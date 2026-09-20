"""Namespaced subject lifecycle: register / get / delete / info.

Write-path receipts, ``library_revision`` monotonicity and namespace isolation.
"""

from __future__ import annotations

from conftest import make_blank_image, make_image

from face_service.store import FaceStore


def test_register_receipt_has_no_embedding(client, register):
    image = make_image(seed=50)
    resp = register(client, "ns-r", "carol", image)
    assert resp.status_code == 201
    body = resp.json()
    assert body["subject_id"] == "carol"
    assert body["namespace"] == "ns-r"
    assert body["created"] is True
    assert body["embedding_dim"] == 64
    assert body["model_version"] == "fake-model@0"
    assert body["library_revision"] == 1
    assert body["quality"]["det_score"] == 0.99
    assert "embedding" not in body
    assert "created_at" in body and "updated_at" in body
    assert "request_id" in body


def test_register_duplicate_conflict_409(client, register):
    image = make_image(seed=51)
    assert register(client, "ns-r2", "carol", image).status_code == 201
    resp = register(client, "ns-r2", "carol", image)
    assert resp.status_code == 409
    body = resp.json()["error"]
    assert body["code"] == "SUBJECT_ALREADY_EXISTS"
    assert body["retryable"] is False


def test_register_overwrite_increments_revision(client, register, settings):
    image = make_image(seed=52)
    assert register(client, "ns-r3", "carol", image).status_code == 201
    assert FaceStore(settings.db_path).revision() == 1
    resp = register(client, "ns-r3", "carol", make_image(seed=53), on_exists="overwrite")
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is False
    assert body["library_revision"] == 2
    assert FaceStore(settings.db_path).revision() == 2


def test_get_subject_metadata_has_no_embedding(client, register):
    image = make_image(seed=54)
    assert register(client, "ns-g", "dave", image).status_code == 201
    resp = client.get("/v1/namespaces/ns-g/subjects/dave")
    assert resp.status_code == 200
    body = resp.json()
    assert body["subject_id"] == "dave"
    assert body["embedding_dim"] == 64
    assert "embedding" not in body
    assert body["library_revision"] == 1
    assert "quality" in body
    assert "request_id" in body


def test_get_missing_subject_and_namespace(client, register):
    assert register(client, "ns-g2", "dave", make_image(seed=55)).status_code == 201
    assert client.get("/v1/namespaces/ns-g2/subjects/absent").status_code == 404
    assert client.get("/v1/namespaces/ghost/subjects/dave").status_code == 404
    assert client.get("/v1/namespaces/ghost/subjects/dave").json()["error"]["code"] == (
        "NAMESPACE_NOT_FOUND"
    )


def test_namespace_isolation(client, register, verify):
    alice = make_image(seed=56)
    bob = make_image(seed=57)
    assert register(client, "ns-a", "shared-id", alice).status_code == 201
    assert register(client, "ns-b", "shared-id", bob).status_code == 201

    # The same subject id is a distinct entity per namespace.
    a = client.get("/v1/namespaces/ns-a/subjects/shared-id").json()
    b = client.get("/v1/namespaces/ns-b/subjects/shared-id").json()
    assert a["namespace"] == "ns-a" and b["namespace"] == "ns-b"

    # Cross-namespace verify resolves the requested namespace's subject only.
    assert verify(client, "ns-a", "shared-id", alice).json()["matched"] is True
    assert verify(client, "ns-a", "shared-id", bob).json()["matched"] is False

    # A subject that exists only in ns-a is invisible in ns-b.
    assert register(client, "ns-b", "only-a", make_image(seed=58)).status_code == 201
    assert client.get("/v1/namespaces/ns-b/subjects/only-a").status_code == 200
    assert client.get("/v1/namespaces/ns-a/subjects/only-a").status_code == 404


def test_info_counts_and_revision(client, register):
    assert client.get("/v1/namespaces/ns-i/info").status_code == 404
    assert register(client, "ns-i", "s1", make_image(seed=60)).status_code == 201
    assert register(client, "ns-i", "s2", make_image(seed=61)).status_code == 201
    info = client.get("/v1/namespaces/ns-i/info").json()
    assert info["subject_count"] == 2
    assert info["library_revision"] == 2
    assert info["model_version"] == "fake-model@0"
    assert "request_id" in info


def test_delete_receipt_and_idempotency(client, register, settings):
    assert register(client, "ns-d", "eve", make_image(seed=62)).status_code == 201
    resp = client.delete("/v1/namespaces/ns-d/subjects/eve")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is True
    assert body["library_revision"] == 2
    assert "request_id" in body
    # Second delete of the same subject is a 404 (documented non-idempotent 404).
    again = client.delete("/v1/namespaces/ns-d/subjects/eve")
    assert again.status_code == 404
    assert again.json()["error"]["code"] == "SUBJECT_NOT_FOUND"
    # Deleting a missing subject does not advance the revision.
    assert FaceStore(settings.db_path).revision() == 2


def test_delete_unknown_namespace(client):
    resp = client.delete("/v1/namespaces/ghost/subjects/eve")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NAMESPACE_NOT_FOUND"


def test_register_no_face_and_multi_face(client, register):
    resp = register(client, "ns-rf", "noface", make_blank_image())
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NO_FACE"


def test_register_multi_face(client, make_client):
    from face_service.model import FaceDetection, FakeModel

    from conftest import synthetic_embedding

    img = make_image(seed=63)
    detections = [
        FaceDetection(bbox=(0.0, 0.0, 10.0, 10.0), det_score=0.9,
                      embedding=synthetic_embedding(img + b"a")),
        FaceDetection(bbox=(0.0, 0.0, 20.0, 20.0), det_score=0.9,
                      embedding=synthetic_embedding(img + b"b")),
    ]
    client2 = make_client(model=FakeModel(detections=detections))
    resp = client2.post(
        "/v1/namespaces/ns-mf/subjects",
        files={"image": ("f.png", img, "image/png")},
        data={"subject_id": "x"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MULTI_FACES_AMBIGUOUS"


def test_register_require_liveness_refused(client):
    resp = client.post(
        "/v1/namespaces/ns-lv/subjects",
        files={"image": ("f.png", make_image(seed=64), "image/png")},
        data={"subject_id": "x", "require_liveness": "true"},
    )
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "LIVENESS_UNSUPPORTED"


def test_register_invalid_subject_id(client, register):
    resp = register(client, "ns-bad", "not allowed!", make_image(seed=65))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"
