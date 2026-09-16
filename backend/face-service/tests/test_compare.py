"""``POST /v1/compare`` — image↔image 1:1 comparison (contract §5).

Backs ``FacePort.same_person``.  The properties locked here are the ones the
Worker relies on and the ones that must never silently regress:

* it compares two **probe** images and reads no subject (so it cannot disclose
  library contents);
* it is **zero-write** (``library_revision`` never advances);
* multi-face input is refused rather than resolved by picking the largest face;
* poor quality can never confirm "same person";
* liveness is reported ``supported=false`` and ``require_liveness`` is *ignored*
  rather than answered with a fabricated ``passed``;
* a client ``threshold`` is honoured here (unlike search) because nothing is
  looked up in a namespace.
"""

from __future__ import annotations

from conftest import make_blank_image, make_image
from face_service.store import FaceStore

NS = "ns-cmp"


def _compare(client, image_a: bytes, image_b: bytes, **data):
    return client.post(
        "/v1/compare",
        files={
            "image_a": ("a.png", image_a, "image/png"),
            "image_b": ("b.png", image_b, "image/png"),
        },
        data={k: str(v) for k, v in data.items()},
    )


# --------------------------------------------------------------------------
# 1. happy path + exact response shape
# --------------------------------------------------------------------------
def test_compare_same_image_matches_with_full_shape(client):
    image = make_image(seed=300)
    resp = _compare(client, image, image)
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is True
    assert body["similarity"] > 0.99
    assert body["threshold"] == 0.40
    assert body["face_count_a"] == 1
    assert body["face_count_b"] == 1
    assert body["reasons"] == []
    # Quality blocks for BOTH probes, so the caller can tell which view failed.
    assert body["quality_a"]["min_acceptable"] is True
    assert body["quality_b"]["min_acceptable"] is True
    assert body["model_version"] == "fake-model@0"
    assert "library_revision" in body
    assert "request_id" in body


def test_compare_different_images_do_not_match(client):
    resp = _compare(client, make_image(seed=301), make_image(seed=302))
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is False
    assert body["similarity"] < 0.01
    # A non-match is a business answer, not an error: still 200, no error body.
    assert "error" not in body


# --------------------------------------------------------------------------
# 2. liveness honesty (MVP has no liveness model)
# --------------------------------------------------------------------------
def test_compare_reports_liveness_unsupported_and_never_fakes_passed(client):
    image = make_image(seed=303)
    body = _compare(client, image, image).json()
    assert body["liveness"] == {
        "supported": False,
        "reason": "buffalo_l has no liveness model",
    }
    assert "passed" not in body["liveness"]
    # The quality blocks must not smuggle a liveness verdict either.
    assert "passed" not in body["quality_a"]
    assert "passed" not in body["quality_b"]


def test_compare_ignores_require_liveness_instead_of_claiming_a_check(client):
    """``/v1/compare`` has no liveness gate to honour, so the field is ignored.

    Answering 200 with ``liveness.supported=false`` is the honest response;
    silently reporting ``passed=true`` (or pretending a check ran) would not be.
    """
    image = make_image(seed=304)
    resp = _compare(client, image, image, require_liveness="true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is True
    assert body["liveness"]["supported"] is False
    assert "passed" not in body["liveness"]


# --------------------------------------------------------------------------
# 3. zero writes
# --------------------------------------------------------------------------
def test_compare_is_zero_write(client, settings):
    store = FaceStore(settings.db_path)
    before = store.revision()
    image = make_image(seed=305)
    for _ in range(3):
        assert _compare(client, image, image).status_code == 200
        assert _compare(client, image, make_image(seed=306)).status_code == 200
    assert store.revision() == before
    # It must not create a namespace either (compare takes no namespace at all).
    assert client.get("/v1/health").json()["library_revision"] == before


def test_compare_does_not_read_or_disclose_library_contents(client, register, settings):
    """A registered subject must be invisible to compare (it reads no subject)."""
    image = make_image(seed=307)
    assert register(client, NS, "alice", image).status_code == 201
    body = _compare(client, image, image).json()
    # No subject identity may leak through a probe-to-probe comparison.
    assert "subject_id" not in body
    assert "namespace" not in body
    assert "alice" not in body.keys()
    assert "embedding" not in body
    assert "candidates" not in body


# --------------------------------------------------------------------------
# 4. conservative refusals
# --------------------------------------------------------------------------
def test_compare_refuses_multi_face_on_either_side(client, make_client):
    from conftest import FaceDetection, make_fake_model, synthetic_embedding

    def two_faces(image_bytes: bytes) -> list[FaceDetection]:
        emb = synthetic_embedding(image_bytes)
        return [
            FaceDetection(bbox=(0.0, 0.0, 32.0, 64.0), det_score=0.99, embedding=emb),
            FaceDetection(bbox=(32.0, 0.0, 64.0, 64.0), det_score=0.98, embedding=emb),
        ]

    c = make_client(model=make_fake_model(detect_fn=two_faces))
    image = make_image(seed=308)
    resp = _compare(c, image, image)
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == "MULTI_FACES_AMBIGUOUS"
    # Both counts are reported so the caller knows which probe was ambiguous.
    assert err["details"]["face_count_a"] == 2
    assert err["details"]["face_count_b"] == 2


def test_compare_blank_image_is_no_face(client):
    resp = _compare(client, make_blank_image(), make_image(seed=309))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NO_FACE"
    resp2 = _compare(client, make_image(seed=310), make_blank_image())
    assert resp2.status_code == 400
    assert resp2.json()["error"]["code"] == "NO_FACE"


def test_compare_poor_quality_can_never_confirm_same_person(make_client, settings):
    """Fail-closed: quality below minimum caps ``matched`` at False.

    Discriminative by construction — the two probes are the *same* image
    (similarity 1.0, far above the 0.40 threshold), so the only thing that can
    make ``matched`` False is the quality gate.
    """
    from dataclasses import replace

    from conftest import make_fake_model

    # A model whose detections always fail the quality floor (det_score too low).
    low_quality = make_fake_model()
    c = make_client(
        model=low_quality,
        settings_override=replace(settings, quality_min_det_score=0.995),
    )
    image = make_image(seed=311)
    body = _compare(c, image, image).json()
    assert body["similarity"] > 0.99
    assert body["matched"] is False
    assert "quality_below_minimum" in body["reasons"]


# --------------------------------------------------------------------------
# 5. threshold handling + request validation
# --------------------------------------------------------------------------
def test_compare_ignores_client_threshold(client, settings):
    """The threshold is server-fixed; a client value is IGNORED, not validated.

    Oracle r29 IMPORTANT: ``threshold`` directly decides the ``same_person``
    verdict, so a caller who could lower it to 0.0 could declare any two
    unrelated images the same person.  "This endpoint reads no library" does not
    make that safe, and ``FacePort.same_person(images)`` takes no threshold, so no
    consumer needs one.  Discriminative: ``threshold=0.0`` on two ORTHOGONAL
    images (similarity ~0.0) would be ``matched=true`` if the value were parsed.
    """
    a, b = make_image(seed=312), make_image(seed=313)
    assert _compare(client, a, b).json()["matched"] is False
    for hostile in ("0.0", "0", "-1.0"):
        body = _compare(client, a, b, threshold=hostile).json()
        assert body["matched"] is False, hostile
        assert body["threshold"] == settings.verify_threshold, hostile
    # A stricter-looking client value is ignored too: the server value governs.
    same = _compare(client, a, a, threshold="0.999").json()
    assert same["threshold"] == settings.verify_threshold
    assert same["matched"] is True  # similarity is exactly 1.0


def test_compare_threshold_comes_from_server_config(make_client, settings):
    """Positive control: the server-side threshold really does govern compare."""
    from dataclasses import replace

    img = make_image(seed=318)
    other = make_image(seed=319)
    strict = make_client(settings_override=replace(settings, verify_threshold=0.9999))
    assert _compare(strict, img, img).json()["matched"] is True   # similarity 1.0
    body = _compare(strict, img, other).json()
    assert body["threshold"] == 0.9999
    assert body["matched"] is False
    lenient = make_client(settings_override=replace(settings, verify_threshold=0.0001))
    assert _compare(lenient, img, img).json()["threshold"] == 0.0001


def test_compare_never_errors_on_a_client_threshold_it_ignores(client, settings):
    """Garbage in an ignored field must not change the outcome either way.

    The field is not parsed, so a non-numeric value is simply discarded rather
    than turned into a 400 — and, more importantly, it can never influence
    ``matched``.  (Under the previous design these values were validated and
    rejected; validation implied the value was being honoured, which was the
    actual defect.)
    """
    image = make_image(seed=314)
    for ignored in ("1.7", "-0.2", "abc", "", "0.0"):
        resp = _compare(client, image, image, threshold=ignored)
        assert resp.status_code == 200, ignored
        body = resp.json()
        assert body["threshold"] == settings.verify_threshold, ignored
        assert body["matched"] is True, ignored


def test_compare_requires_both_images(client):
    image = make_image(seed=315)
    resp = client.post(
        "/v1/compare", files={"image_a": ("a.png", image, "image/png")}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"
    assert "image_b" in resp.json()["error"]["message"]


def test_compare_accepts_json_base64_payload(client):
    """Same decoding path as the single-image endpoints (contract §5.1)."""
    import base64

    image = make_image(seed=316)
    encoded = base64.b64encode(image).decode("ascii")
    resp = client.post(
        "/v1/compare",
        json={"image_a_base64": encoded, "image_b_base64": f"data:image/png;base64,{encoded}"},
    )
    assert resp.status_code == 200
    assert resp.json()["matched"] is True


def test_compare_rejects_unsupported_media_type(client):
    resp = client.post("/v1/compare", content=b"image_a,image_b", headers={
        "content-type": "text/csv"
    })
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


# --------------------------------------------------------------------------
# 6. auth
# --------------------------------------------------------------------------
def test_compare_requires_token(make_client):
    from face_service.auth import TokenAuth

    c = make_client(auth=TokenAuth("SECRET-TOKEN-DO-NOT-USE"))
    image = make_image(seed=317)
    anon = c.post(
        "/v1/compare",
        files={
            "image_a": ("a.png", image, "image/png"),
            "image_b": ("b.png", image, "image/png"),
        },
    )
    assert anon.status_code == 401
    assert anon.json()["error"]["code"] == "UNAUTHORIZED"
    ok = c.post(
        "/v1/compare",
        files={
            "image_a": ("a.png", image, "image/png"),
            "image_b": ("b.png", image, "image/png"),
        },
        headers={"X-Internal-Token": "SECRET-TOKEN-DO-NOT-USE"},
    )
    assert ok.status_code == 200
