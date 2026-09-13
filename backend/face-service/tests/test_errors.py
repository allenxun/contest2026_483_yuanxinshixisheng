"""Stable error codes, HTTP mapping, retryable flags and envelope shape."""

from __future__ import annotations

from conftest import make_image

from face_service.errors import ERROR_SPECS, ErrorCode

REQUIRED = {
    "NO_FACE": (400, False),
    "MULTI_FACES_AMBIGUOUS": (400, False),
    "IMAGE_DECODE_FAILED": (400, False),
    "IMAGE_TOO_LARGE": (413, False),
    "UNSUPPORTED_MEDIA_TYPE": (415, False),
    "SUBJECT_NOT_FOUND": (404, False),
    "NAMESPACE_NOT_FOUND": (404, False),
    "SUBJECT_ALREADY_EXISTS": (409, False),
    "QUALITY_INSUFFICIENT": (422, False),
    "MODEL_UNAVAILABLE": (503, True),
    "MODEL_NOT_LOADED": (503, True),
    "LIVENESS_UNSUPPORTED": (501, False),
    "UNAUTHORIZED": (401, False),
    "INTERNAL_ERROR": (500, True),
}


def test_error_code_table_is_complete_and_stable():
    for name, (status, retryable) in REQUIRED.items():
        code = ErrorCode(name)
        spec = ERROR_SPECS[code]
        assert spec.http_status == status, name
        assert spec.retryable is retryable, name
        assert spec.description


def test_error_envelope_shape(client, extract):
    resp = extract(client, b"not-an-image")
    assert resp.status_code == 400
    body = resp.json()
    assert set(body) == {"error"}
    err = body["error"]
    assert set(err) >= {"code", "message", "retryable", "request_id"}
    assert err["code"] == "IMAGE_DECODE_FAILED"
    assert isinstance(err["retryable"], bool)


def test_request_id_is_echoed_when_valid(client, extract):
    resp = extract(client, make_image(1))
    # TestClient supplies the header on the response; the body carries the same.
    header_rid = resp.headers.get("X-Request-Id")
    assert header_rid
    assert resp.json()["request_id"] == header_rid


def test_request_id_generated_and_sanitized(client, extract):
    resp = client.post(
        "/v1/extract",
        files={"image": ("f.png", make_image(2), "image/png")},
        headers={"X-Request-Id": "bad id with spaces/and\nnewline"},
    )
    rid = resp.headers.get("X-Request-Id")
    assert rid
    assert " " not in rid and "\n" not in rid
    assert rid != "bad id with spaces/and\nnewline"


def test_unknown_route_returns_envelope(client):
    resp = client.get("/v1/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] in {"INVALID_REQUEST", "NAMESPACE_NOT_FOUND"}


def test_quality_insufficient_when_enforced(make_client, tmp_path):
    from face_service.config import Settings
    from face_service.model import FaceDetection, FakeModel

    from conftest import make_image, synthetic_embedding

    img = make_image(seed=99)
    # Tiny bbox -> area ratio below the 0.02 minimum -> min_acceptable False.
    det = FaceDetection(bbox=(0.0, 0.0, 1.0, 1.0), det_score=0.99,
                        embedding=synthetic_embedding(img))
    custom = Settings(
        # Loopback + explicit auth-off: this isolated TestClient exercises
        # quality gating, not auth. The new fail-closed default would otherwise
        # (correctly) refuse to construct a non-authenticated config.
        host="127.0.0.1",
        auth_required=False,
        port=18099,
        data_dir=tmp_path,
        db_path=tmp_path / "faces.sqlite3",
        verify_threshold=0.40,
        max_body_bytes=1024 * 1024,
        inference_timeout_seconds=5.0,
        max_concurrency=4,
        quality_enforce=True,
        quality_min_bbox_ratio=0.02,
    )
    client = make_client(model=FakeModel(detections=[det]), settings_override=custom)
    resp = client.post(
        "/v1/namespaces/q-insuf/subjects",
        files={"image": ("f.png", img, "image/png")},
        data={"subject_id": "s"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "QUALITY_INSUFFICIENT"


def test_model_not_loaded_maps_to_503(make_client, settings):
    from face_service.model import FakeModel

    model = FakeModel(loaded=False, load_error=True)
    client = make_client(model=model)
    resp = client.post(
        "/v1/extract", files={"image": ("f.png", make_image(3), "image/png")}
    )
    assert resp.status_code == 503
    body = resp.json()["error"]
    assert body["code"] == "MODEL_UNAVAILABLE"
    assert body["retryable"] is True
