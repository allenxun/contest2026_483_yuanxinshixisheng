"""``/live`` and ``/ready`` probes, and proof that ``/v1/health`` is unchanged.

``/live`` proves the process is up.  ``/ready`` proves the model is loaded and
SQLite is reachable, and must fail (non-2xx) otherwise -- unlike ``/v1/health``,
which stays 200 + ``degraded``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import make_fake_model

from face_service.app import create_app
from face_service.auth import TokenAuth
from face_service.model import FakeModel
from face_service.store import FaceStore


def test_live_and_ready_ok(client):
    live = client.get("/live")
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}

    ready = client.get("/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["model_loaded"] is True
    assert body["model_version"] == "fake-model@0"
    assert isinstance(body["library_revision"], int)


def test_live_still_200_when_model_not_loaded(make_client):
    client = make_client(model=FakeModel(loaded=False, load_error=True))
    assert client.get("/live").status_code == 200
    assert client.get("/live").json() == {"status": "alive"}


def test_ready_503_model_not_loaded_while_live_ok(make_client):
    client = make_client(model=FakeModel(loaded=False, load_error=True))
    resp = client.get("/ready")
    assert resp.status_code == 503
    err = resp.json()["error"]
    assert err["code"] == "MODEL_NOT_LOADED"
    assert err["retryable"] is True
    # Separation of the two probes is the whole point.
    assert client.get("/live").status_code == 200


def test_health_still_200_degraded_when_model_not_loaded(make_client):
    """Guard: the pre-existing ``/v1/health`` semantics must not change."""
    client = make_client(model=FakeModel(loaded=False, load_error=True))
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"
    assert resp.json()["model_loaded"] is False


class _BrokenStore(FaceStore):
    """A store whose only failure is a read: used to exercise /ready's 503."""

    def revision(self) -> int:  # type: ignore[override]
        raise OSError("simulated sqlite outage at /private/path/f.db")


def test_ready_503_store_unavailable(settings):
    store = _BrokenStore(settings.db_path)
    app = create_app(
        settings=settings,
        model=make_fake_model(),
        store=store,
        auth=TokenAuth(None),
    )
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 503
    err = resp.json()["error"]
    assert err["code"] == "STORE_UNAVAILABLE"
    assert err["retryable"] is True
    # The failure body must not leak the path or the underlying message.
    assert "simulated sqlite outage" not in resp.text
    assert "/private/path" not in resp.text


def test_ready_body_has_no_identity_or_network_fields(client):
    body = client.get("/ready").json()
    assert set(body) == {"status", "model_loaded", "model_version", "library_revision"}
    for forbidden in ("namespace", "subject_count", "host", "port", "path", "token", "liveness"):
        assert forbidden not in body
        assert forbidden not in client.get("/live").json()


def test_live_and_ready_are_public(make_client):
    client = make_client(auth=TokenAuth("secret-token-value", "X-Internal-Token"))
    assert client.get("/live").status_code == 200
    assert client.get("/ready").status_code == 200