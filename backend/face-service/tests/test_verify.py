"""``/v1/verify``: strict 1:1 against the named subject; no whole-library search."""

from __future__ import annotations

from conftest import make_blank_image, make_image

from face_service.store import FaceStore


def test_verify_matching_subject(client, register, verify):
    image = make_image(seed=30)
    assert register(client, "ns-v", "alice", image).status_code == 201
    resp = verify(client, "ns-v", "alice", image)
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is True
    assert body["similarity"] > 0.99
    assert body["threshold"] == 0.40
    assert body["face_count"] == 1
    assert body["subject_id"] == "alice"
    assert body["namespace"] == "ns-v"
    assert body["liveness"] == {"supported": False, "reason": "buffalo_l has no liveness model"}
    assert body["library_revision"] >= 1


def test_verify_does_not_degrade_to_global_top1(client, register, verify):
    """Discriminative: a different face must be a MISMATCH, not top1/not-found.

    Two subjects are registered in the same namespace.  Verifying subject
    ``alice`` with Bob's image must return ``matched=false`` and must NOT leak
    Bob as a match (which a whole-library top1 would do).
    """
    alice_img = make_image(seed=31)
    bob_img = make_image(seed=32)
    assert register(client, "ns-v2", "alice", alice_img).status_code == 201
    assert register(client, "ns-v2", "bob", bob_img).status_code == 201

    resp = verify(client, "ns-v2", "alice", bob_img)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["matched"] is False
    assert body["subject_id"] == "alice"  # never switches to Bob (top1)
    assert body["similarity"] < body["threshold"]

    # Sanity: alice still matches her own image.
    assert verify(client, "ns-v2", "alice", alice_img).json()["matched"] is True


def test_verify_unknown_subject_is_not_found_not_top1(client, register, verify):
    assert register(client, "ns-v3", "alice", make_image(seed=33)).status_code == 201
    resp = verify(client, "ns-v3", "does-not-exist", make_image(seed=34))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SUBJECT_NOT_FOUND"


def test_verify_unknown_namespace(client, verify):
    resp = verify(client, "no-such-ns", "alice", make_image(seed=35))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NAMESPACE_NOT_FOUND"


def test_verify_no_face(client, register, verify):
    assert register(client, "ns-v4", "alice", make_image(seed=36)).status_code == 201
    resp = verify(client, "ns-v4", "alice", make_blank_image())
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NO_FACE"


def test_verify_multi_face_ambiguous(client, make_client, register):
    from face_service.model import FaceDetection, FakeModel

    from conftest import synthetic_embedding

    image = make_image(seed=37)
    assert register(client, "ns-v5", "alice", image).status_code == 201

    img = make_image(seed=38)
    detections = [
        FaceDetection(bbox=(0.0, 0.0, 10.0, 10.0), det_score=0.9,
                      embedding=synthetic_embedding(img + b"a")),
        FaceDetection(bbox=(0.0, 0.0, 20.0, 20.0), det_score=0.9,
                      embedding=synthetic_embedding(img + b"b")),
    ]
    client2 = make_client(model=FakeModel(detections=detections))
    resp = client2.post(
        "/v1/verify",
        files={"image": ("f.png", img, "image/png")},
        data={"namespace": "ns-v5", "subject_id": "alice"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MULTI_FACES_AMBIGUOUS"


def test_verify_is_zero_write(client, register, verify, settings):
    image = make_image(seed=39)
    assert register(client, "ns-v6", "alice", image).status_code == 201
    before = FaceStore(settings.db_path).revision()
    assert verify(client, "ns-v6", "alice", image).status_code == 200
    assert verify(client, "ns-v6", "nobody", image).status_code == 404
    assert FaceStore(settings.db_path).revision() == before


def test_verify_require_liveness_is_refused_not_faked(client, register):
    assert register(client, "ns-v7", "alice", make_image(seed=40)).status_code == 201
    resp = client.post(
        "/v1/verify",
        files={"image": ("f.png", make_image(seed=40), "image/png")},
        data={"namespace": "ns-v7", "subject_id": "alice", "require_liveness": "true"},
    )
    assert resp.status_code == 501
    body = resp.json()["error"]
    assert body["code"] == "LIVENESS_UNSUPPORTED"
    assert body["retryable"] is False


def test_verify_invalid_threshold(client, register):
    assert register(client, "ns-v8", "alice", make_image(seed=41)).status_code == 201
    resp = client.post(
        "/v1/verify",
        files={"image": ("f.png", make_image(seed=41), "image/png")},
        data={"namespace": "ns-v8", "subject_id": "alice", "threshold": "1.5"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


def test_verify_threshold_override_controls_match(client, register):
    image = make_image(seed=42)
    assert register(client, "ns-v9", "alice", image).status_code == 201
    # Same image: similarity is 1.0, so even a 1.0 threshold matches.
    resp = client.post(
        "/v1/verify",
        files={"image": ("f.png", image, "image/png")},
        data={"namespace": "ns-v9", "subject_id": "alice", "threshold": "1.0"},
    )
    assert resp.status_code == 200
    assert resp.json()["threshold"] == 1.0
    assert resp.json()["matched"] is True
