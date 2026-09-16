"""Idempotent registration + reconciliation lookup (contract §6).

Backs ``FacePort.register_person`` / ``FacePort.query_registration``.  The
Worker calls register **outside** its lease and may lose the response; it then
reconciles with the *same* correlation id instead of minting another one
(``identity_enroll.py:173`` — "同 EntityId 对账，绝不生成另一 ID 盲重试").

Locked here:
* same ``correlation_id`` → idempotent replay: **no overwrite, no revision bump**;
* different ``correlation_id`` on an existing subject → 409, never a silent
  replacement of the stored reference image;
* callers that send no correlation id keep the **exact** pre-existing behaviour;
* the reconciliation lookup is read-only, namespace-scoped, minimum-disclosure,
  and reports only ``registered`` / ``not_found`` (``unknown`` is a client-side
  transport state and is never fabricated by the service).
"""

from __future__ import annotations

from conftest import make_image
from face_service.store import FaceStore

NS = "ns-reg"
CORR = "corr-0001"
PRR = "prr-0001"


def _register(client, subject_id: str, image: bytes, **data):
    return client.post(
        f"/v1/namespaces/{NS}/subjects",
        files={"image": ("f.png", image, "image/png")},
        data={"subject_id": subject_id, **{k: str(v) for k, v in data.items()}},
    )


def _recon(client, correlation_id: str, **params):
    return client.get(
        f"/v1/namespaces/{NS}/registrations/{correlation_id}",
        params={k: str(v) for k, v in params.items()},
    )


# --------------------------------------------------------------------------
# 1. idempotent replay
# --------------------------------------------------------------------------
def test_first_register_creates_and_persists_reconciliation_keys(client):
    resp = _register(client, "s1", make_image(seed=400), correlation_id=CORR,
                     provider_request_id=PRR)
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] is True
    assert body["replayed"] is False
    assert body["library_revision"] == 1
    assert body["registered_at"]
    assert body["subject_id"] == "s1"
    # The reconciliation keys themselves are not echoed back as secrets, but the
    # lookup below proves they were persisted.
    assert "correlation_id" not in body


def test_same_correlation_id_replays_without_overwrite_or_revision_bump(client, settings):
    """The core idempotency guarantee.

    The retry sends a **different image**: if the implementation overwrote the
    stored embedding, ``updated_at`` would change and a later search with the
    original image would stop matching.  Both are asserted, so this test is
    discriminative rather than a tautology.
    """
    original = make_image(seed=401)
    different = make_image(seed=402)
    first = _register(client, "s2", original, correlation_id=CORR, provider_request_id=PRR)
    assert first.status_code == 201
    rev1 = first.json()["library_revision"]
    updated1 = first.json()["updated_at"]

    replay = _register(client, "s2", different, correlation_id=CORR)
    assert replay.status_code == 200
    body = replay.json()
    assert body["created"] is False
    assert body["replayed"] is True
    # No revision bump: a retry must not look like a library change.
    assert body["library_revision"] == rev1
    # No overwrite: the stored row is untouched.
    assert body["updated_at"] == updated1
    assert FaceStore(settings.db_path).count_subjects(NS) == 1
    # The ORIGINAL embedding still governs search.
    hit = client.post(
        f"/v1/namespaces/{NS}/search",
        files={"image": ("f.png", original, "image/png")},
    ).json()
    assert hit["decision"] == "matched"
    assert hit["subject_id"] == "s2"
    miss = client.post(
        f"/v1/namespaces/{NS}/search",
        files={"image": ("f.png", different, "image/png")},
    ).json()
    assert miss["decision"] != "matched"


def test_different_correlation_id_on_existing_subject_is_a_conflict(client, settings):
    image = make_image(seed=403)
    assert _register(client, "s3", image, correlation_id=CORR).status_code == 201
    other = _register(client, "s3", make_image(seed=404), correlation_id="corr-OTHER")
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "SUBJECT_ALREADY_EXISTS"
    # Still exactly one subject, and the original reference image is intact.
    assert FaceStore(settings.db_path).count_subjects(NS) == 1
    hit = client.post(
        f"/v1/namespaces/{NS}/search",
        files={"image": ("f.png", image, "image/png")},
    ).json()
    assert hit["decision"] == "matched" and hit["subject_id"] == "s3"


def test_missing_correlation_id_on_existing_subject_stays_a_conflict(client):
    """A stored correlation id must not be matched by a caller that sends none."""
    assert _register(client, "s4", make_image(seed=405), correlation_id=CORR).status_code == 201
    resp = _register(client, "s4", make_image(seed=406))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SUBJECT_ALREADY_EXISTS"


# --------------------------------------------------------------------------
# 2. backward compatibility (no correlation id at all)
# --------------------------------------------------------------------------
def test_legacy_callers_keep_the_exact_previous_behaviour(client):
    image = make_image(seed=407)
    first = _register(client, "legacy", image)
    assert first.status_code == 201
    assert first.json()["created"] is True
    assert first.json()["replayed"] is False
    dup = _register(client, "legacy", image)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "SUBJECT_ALREADY_EXISTS"
    over = _register(client, "legacy", make_image(seed=408), on_exists="overwrite")
    assert over.status_code == 200
    assert over.json()["created"] is False
    assert over.json()["replayed"] is False
    assert over.json()["library_revision"] > first.json()["library_revision"]


def test_overwrite_records_the_new_reconciliation_keys(client):
    image = make_image(seed=409)
    _register(client, "ow", image, correlation_id="corr-a", provider_request_id="prr-a")
    resp = _register(client, "ow", make_image(seed=410), correlation_id="corr-b",
                     provider_request_id="prr-b", on_exists="overwrite")
    assert resp.status_code == 200
    # The old correlation id no longer resolves; the new one does.
    assert _recon(client, "corr-a").json()["status"] == "not_found"
    found = _recon(client, "corr-b").json()
    assert found["status"] == "registered"
    assert found["subject_id"] == "ow"
    assert found["provider_request_id"] == "prr-b"


# --------------------------------------------------------------------------
# 3. reconciliation lookup
# --------------------------------------------------------------------------
def test_recon_returns_registered_with_minimum_disclosure(client):
    _register(client, "r1", make_image(seed=411), correlation_id="corr-r1",
              provider_request_id="prr-r1")
    resp = _recon(client, "corr-r1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "registered"
    assert body["subject_id"] == "r1"
    assert body["correlation_id"] == "corr-r1"
    assert body["provider_request_id"] == "prr-r1"
    assert body["registered_at"]
    assert "library_revision" in body and "request_id" in body
    # Minimum disclosure: never an embedding, quality block, bbox or listing.
    for forbidden in ("embedding", "quality", "bbox", "det_score", "subjects",
                      "candidates", "namespace"):
        assert forbidden not in body, forbidden


def test_recon_unknown_correlation_is_not_found_without_writes(client, settings):
    """An unknown correlation id in an EXISTING namespace is a 200 ``not_found``.

    The namespace must exist first: a *missing* namespace is a different contract
    branch (404 ``NAMESPACE_NOT_FOUND``, covered by
    :func:`test_recon_unknown_namespace_is_404_and_not_created`).  ``not_found``
    is a normal business answer — the Worker branches on ``status``, not on the
    HTTP code (``identity_enroll.py:188``), so this must not be an error status.
    """
    assert _register(client, "anchor", make_image(seed=417),
                     correlation_id="corr-anchor").status_code == 201
    store = FaceStore(settings.db_path)
    before = store.revision()
    resp = _recon(client, "corr-never-registered")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "not_found"
    assert set(body) == {"status", "request_id"}
    # Read-only: the lookup advanced nothing and created nothing.
    assert store.revision() == before
    assert store.count_subjects(NS) == 1


def test_recon_never_reports_unknown(client):
    """``unknown`` is a client-side transport state; the service must not fake it."""
    _register(client, "r2", make_image(seed=412), correlation_id="corr-r2")
    for params in ({}, {"entity_id": "r2"}, {"entity_id": "wrong"},
                   {"provider_request_id": "wrong"}):
        body = _recon(client, "corr-r2", **params).json()
        assert body["status"] in ("registered", "not_found"), params
    body = _recon(client, "corr-missing").json()
    assert body["status"] == "not_found"


def test_recon_tightening_params_must_agree(client):
    _register(client, "r3", make_image(seed=413), correlation_id="corr-r3",
              provider_request_id="prr-r3")
    assert _recon(client, "corr-r3", entity_id="r3").json()["status"] == "registered"
    assert _recon(client, "corr-r3", entity_id="other").json()["status"] == "not_found"
    assert _recon(client, "corr-r3", provider_request_id="prr-r3").json()["status"] == "registered"
    assert _recon(client, "corr-r3", provider_request_id="prr-X").json()["status"] == "not_found"
    both = _recon(client, "corr-r3", entity_id="r3", provider_request_id="prr-r3")
    assert both.json()["status"] == "registered"


def test_recon_is_namespace_scoped(client):
    """The same correlation id in another namespace must not resolve here."""
    _register(client, "r4", make_image(seed=414), correlation_id="corr-shared")
    other_ns = client.post(
        "/v1/namespaces/ns-other/subjects",
        files={"image": ("f.png", make_image(seed=415), "image/png")},
        data={"subject_id": "r4", "correlation_id": "corr-shared"},
    )
    assert other_ns.status_code == 201
    assert _recon(client, "corr-shared").json()["subject_id"] == "r4"
    assert client.get("/v1/namespaces/ns-other/registrations/corr-shared").json()[
        "status"
    ] == "registered"
    # Deleting in one namespace must not affect the other's reconciliation.
    assert client.delete(f"/v1/namespaces/{NS}/subjects/r4").status_code == 200
    assert _recon(client, "corr-shared").json()["status"] == "not_found"
    assert client.get("/v1/namespaces/ns-other/registrations/corr-shared").json()[
        "status"
    ] == "registered"


def test_recon_unknown_namespace_is_404_and_not_created(client, settings):
    store = FaceStore(settings.db_path)
    before = store.revision()
    resp = client.get("/v1/namespaces/ns-ghost/registrations/corr-x")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NAMESPACE_NOT_FOUND"
    assert store.namespace_exists("ns-ghost") is False
    assert store.revision() == before


def test_recon_rejects_malformed_ids(client):
    for bad in ("has space", "bad*char", "x" * 129):
        resp = client.get(f"/v1/namespaces/{NS}/registrations/{bad}")
        assert resp.status_code == 400, bad
        assert resp.json()["error"]["code"] == "INVALID_REQUEST", bad


def test_register_rejects_malformed_reconciliation_keys(client):
    image = make_image(seed=416)
    for field in ("correlation_id", "provider_request_id"):
        resp = _register(client, "r5", image, **{field: "bad*char"})
        assert resp.status_code == 400, field
        assert resp.json()["error"]["code"] == "INVALID_REQUEST", field


def test_recon_requires_token(make_client):
    from face_service.auth import TokenAuth

    c = make_client(auth=TokenAuth("SECRET-TOKEN-DO-NOT-USE"))
    anon = c.get(f"/v1/namespaces/{NS}/registrations/corr-x")
    assert anon.status_code == 401
    assert anon.json()["error"]["code"] == "UNAUTHORIZED"
