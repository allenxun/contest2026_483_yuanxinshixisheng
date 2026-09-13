"""``/v1/quality`` and the embedded quality block: honest signals only."""

from __future__ import annotations

from conftest import make_blank_image, make_image

from face_service.store import FaceStore


def test_quality_real_metrics_present(client, extract):
    resp = extract(client, make_image(seed=5), namespace="q")
    quality = resp.json()["faces"][0]["quality"]
    assert quality["blur"]["supported"] is True
    assert quality["blur"]["method"] == "laplacian_variance_gray_crop"
    assert quality["blur"]["value"] > 0
    assert quality["illumination"]["supported"] is True
    assert 0.0 <= quality["illumination"]["mean"] <= 255.0
    assert quality["illumination"]["std"] >= 0.0
    assert quality["bbox_area_ratio"] > 0
    assert quality["det_score"] == 0.99
    assert isinstance(quality["min_acceptable"], bool)


def test_quality_unsupported_metrics_are_explicit(client, extract):
    quality = extract(client, make_image(seed=6)).json()["faces"][0]["quality"]
    assert quality["pose"]["supported"] is False
    assert "reason" in quality["pose"]
    assert quality["occlusion"]["supported"] is False
    assert "reason" in quality["occlusion"]
    # Liveness is never derived from det_score / similarity.
    assert quality["liveness"] == {
        "supported": False,
        "reason": "buffalo_l has no liveness model",
    }


def test_quality_endpoint_no_embeddings_and_read_only(client, settings):
    before = FaceStore(settings.db_path).revision()
    img = make_image(seed=7)
    resp = client.post(
        "/v1/quality",
        files={"image": ("f.png", img, "image/png")},
        data={"namespace": "q2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["face_count"] == 1
    face = body["faces"][0]
    assert "quality" in face
    assert "embedding" not in face
    assert body["liveness"]["supported"] is False
    assert FaceStore(settings.db_path).revision() == before
    # namespace echo only; nothing created
    assert client.get("/v1/namespaces/q2/info").status_code == 404


def test_quality_blank_image_no_face(client):
    resp = client.post(
        "/v1/quality", files={"image": ("f.png", make_blank_image(), "image/png")}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NO_FACE"


def test_laplacian_variance_detects_blur_difference():
    import numpy as np

    from face_service.quality import laplacian_variance

    sharp = np.zeros((64, 64), dtype=np.float64)
    sharp[:, 32:] = 255.0
    blurred = np.zeros((64, 64), dtype=np.float64)
    gradient = np.linspace(0, 255, 64)
    blurred[:] = gradient[None, :]
    assert laplacian_variance(sharp) > laplacian_variance(blurred)


def test_quality_thresholds_reported(client, extract):
    quality = extract(client, make_image(seed=8)).json()["faces"][0]["quality"]
    assert quality["thresholds"] == {
        "det_score": 0.5,
        "blur": 30.0,
        "bbox_area_ratio": 0.02,
    }
