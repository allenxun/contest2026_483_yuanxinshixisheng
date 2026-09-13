"""Health endpoint: read-only, no model reload, honest liveness."""

from __future__ import annotations


def test_health_ok_and_read_only(client, settings):
    from face_service.store import FaceStore

    before = FaceStore(settings.db_path).revision()
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["model_version"] == "fake-model@0"
    assert body["library_revision"] == before
    assert body["liveness"] == {"supported": False, "reason": "buffalo_l has no liveness model"}
    assert body["uptime_seconds"] >= 0
    # Read-only: still the same revision afterwards.
    assert FaceStore(settings.db_path).revision() == before


def test_health_reports_model_not_loaded_without_reloading(make_client):
    from face_service.model import FakeModel

    client = make_client(model=FakeModel(loaded=False, load_error=True))
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_loaded"] is False
    assert body["status"] == "degraded"
    assert body["liveness"]["supported"] is False


def test_health_never_calls_model_load_again(make_client):
    from face_service.model import FakeModel

    model = FakeModel(loaded=True)  # no detect_fn needed for health
    client = make_client(model=model)
    calls_after_startup = model.load_calls
    client.get("/v1/health")
    client.get("/v1/health")
    assert model.load_calls == calls_after_startup
