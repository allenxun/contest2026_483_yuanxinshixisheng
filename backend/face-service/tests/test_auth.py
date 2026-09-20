"""Optional internal token authentication."""

from __future__ import annotations

from conftest import make_image

from face_service.auth import TokenAuth

TOKEN = "test-token-do-not-log-0123456789abcdef"


def _auth_client(make_client):
    return make_client(auth=TokenAuth(TOKEN, "X-Internal-Token"))


def test_health_is_public_but_others_require_token(make_client):
    client = _auth_client(make_client)
    assert client.get("/v1/health").status_code == 200

    resp = client.post("/v1/extract", files={"image": ("f.png", make_image(1), "image/png")})
    assert resp.status_code == 401
    body = resp.json()["error"]
    assert body["code"] == "UNAUTHORIZED"
    assert body["retryable"] is False


def test_wrong_token_rejected(make_client):
    client = _auth_client(make_client)
    resp = client.post(
        "/v1/extract",
        files={"image": ("f.png", make_image(1), "image/png")},
        headers={"X-Internal-Token": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_correct_token_allows_access(make_client):
    client = _auth_client(make_client)
    resp = client.post(
        "/v1/extract",
        files={"image": ("f.png", make_image(1), "image/png")},
        headers={"X-Internal-Token": TOKEN},
    )
    assert resp.status_code == 200


def test_error_does_not_echo_token(make_client):
    client = _auth_client(make_client)
    resp = client.post(
        "/v1/extract",
        files={"image": ("f.png", make_image(1), "image/png")},
        headers={"X-Internal-Token": "wrong-" + TOKEN},
    )
    assert TOKEN not in resp.text
    assert "wrong-" not in resp.text


def test_register_and_delete_require_token(make_client):
    client = _auth_client(make_client)
    resp = client.post(
        "/v1/namespaces/ns/subjects",
        files={"image": ("f.png", make_image(2), "image/png")},
        data={"subject_id": "s"},
    )
    assert resp.status_code == 401
    assert client.get("/v1/namespaces/ns/info").status_code == 401
    assert client.delete("/v1/namespaces/ns/subjects/s").status_code == 401
