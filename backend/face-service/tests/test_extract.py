"""``/v1/extract``: pure feature extraction, ZERO writes.

The zero-write assertions here are the discriminative regression against the
legacy ``/extract_face`` defect (search-then-auto-INSERT).
"""

from __future__ import annotations

import base64

from conftest import make_blank_image, make_image

from face_service.store import FaceStore


def test_extract_multipart_returns_embeddings(client, extract):
    image = make_image(seed=1)
    resp = extract(client, image, namespace="ai-skin-mvp")
    assert resp.status_code == 200
    body = resp.json()
    assert body["face_count"] == 1
    assert body["namespace"] == "ai-skin-mvp"
    assert body["model_version"] == "fake-model@0"
    assert "library_revision" in body
    assert body["liveness"]["supported"] is False
    face = body["faces"][0]
    assert set(face) >= {"bbox", "det_score", "embedding", "dim", "quality", "largest_face"}
    assert face["largest_face"] is True
    assert face["dim"] == len(face["embedding"]) == 64
    assert body["largest_face_index"] == 0
    # No library match information is ever returned.
    assert "matched" not in body
    assert "subject_id" not in body
    for item in body["faces"]:
        assert "subject_id" not in item
        assert "similarity" not in item


def test_extract_accepts_base64_json(client):
    image = make_image(seed=2)
    resp = client.post(
        "/v1/extract",
        json={"image_base64": base64.b64encode(image).decode("ascii"), "namespace": "ns-json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["face_count"] == 1
    assert body["namespace"] == "ns-json"
    assert body["faces"][0]["dim"] == 64


def test_extract_accepts_data_url_base64(client):
    image = make_image(seed=3)
    data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
    resp = client.post("/v1/extract", json={"image_base64": data_url})
    assert resp.status_code == 200
    assert resp.json()["face_count"] == 1


def test_extract_blank_image_no_face(client, extract):
    resp = extract(client, make_blank_image())
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NO_FACE"
    assert resp.json()["error"]["retryable"] is False


def test_extract_zero_write_is_discriminative(client, extract, register, settings):
    """extract must not create namespaces or subjects and must not bump revision."""
    # Establish an existing library state first.
    reg = register(client, "ns-a", "sub-1", make_image(seed=10))
    assert reg.status_code == 201
    rev_after_register = FaceStore(settings.db_path).revision()
    assert rev_after_register >= 1
    count_after_register = client.get("/v1/namespaces/ns-a/info").json()["subject_count"]
    assert count_after_register == 1

    resp = extract(client, make_image(seed=11), namespace="ghost-namespace")
    assert resp.status_code == 200
    assert resp.json()["library_revision"] == rev_after_register

    # The namespace referenced in the extract echo must NOT have been created.
    info = client.get("/v1/namespaces/ghost-namespace/info")
    assert info.status_code == 404
    assert info.json()["error"]["code"] == "NAMESPACE_NOT_FOUND"

    # Existing library untouched.
    assert FaceStore(settings.db_path).revision() == rev_after_register
    assert client.get("/v1/namespaces/ns-a/info").json()["subject_count"] == 1


def test_extract_multi_face_reports_all(client, make_client):
    from face_service.model import FaceDetection

    from conftest import synthetic_embedding

    img = make_image(seed=20)
    detections = [
        FaceDetection(bbox=(0.0, 0.0, 10.0, 10.0), det_score=0.9,
                      embedding=synthetic_embedding(img + b"a")),
        FaceDetection(bbox=(0.0, 0.0, 40.0, 40.0), det_score=0.8,
                      embedding=synthetic_embedding(img + b"b")),
    ]
    client2 = make_client(model=make_client_model(detections))
    resp = client2.post("/v1/extract", files={"image": ("f.png", img, "image/png")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["face_count"] == 2
    # Largest bbox (40x40) is flagged.
    assert body["faces"][1]["largest_face"] is True
    assert body["faces"][0]["largest_face"] is False


def make_client_model(detections):
    from face_service.model import FakeModel

    return FakeModel(detections=detections)


def test_extract_unsupported_media_type(client):
    resp = client.post("/v1/extract", content=b"not an image",
                       headers={"content-type": "text/plain"})
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_extract_image_too_large(make_client, settings):
    from dataclasses import replace

    small = replace(settings, max_body_bytes=64)
    client = make_client(settings_override=small)
    resp = client.post(
        "/v1/extract",
        files={"image": ("f.png", make_image(seed=1), "image/png")},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "IMAGE_TOO_LARGE"
    assert resp.json()["error"]["retryable"] is False


def test_extract_bad_base64(client):
    resp = client.post("/v1/extract", json={"image_base64": "!!!not-base64!!!"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "IMAGE_DECODE_FAILED"


def test_extract_invalid_image_bytes(client, extract):
    resp = extract(client, b"definitely-not-an-image")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "IMAGE_DECODE_FAILED"
