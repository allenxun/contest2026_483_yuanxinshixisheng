"""IMPORTANT 5: uvicorn raw access logs disabled; sanitized route-template logging.

The access logger must record the *route template* plus method/status/request_id
and duration -- never the expanded path or real namespace/subject values.
"""

from __future__ import annotations

import logging

from conftest import make_image

from face_service.config import Settings
from face_service.main import uvicorn_run_kwargs

SECRET_NS = "ns-secret-abc"
SECRET_SUBJ = "subj-secret-xyz"
ACCESS_LOGGER = "face_service.access"


def _access_text(caplog) -> str:
    return "\n".join(
        record.getMessage() for record in caplog.records if record.name == ACCESS_LOGGER
    )


def test_uvicorn_raw_access_log_is_disabled():
    settings = Settings(host="127.0.0.1", auth_required=False)
    assert uvicorn_run_kwargs(settings)["access_log"] is False


def test_register_access_log_uses_template_and_hides_values(client, caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        resp = client.post(
            f"/v1/namespaces/{SECRET_NS}/subjects",
            files={"image": ("f.png", make_image(seed=71), "image/png")},
            data={"subject_id": SECRET_SUBJ},
        )
    assert resp.status_code == 201
    text = _access_text(caplog)
    assert "/v1/namespaces/{namespace}/subjects" in text
    assert "method=POST" in text
    assert "status=201" in text
    rid = resp.headers["X-Request-Id"]
    assert f"request_id={rid}" in text
    assert SECRET_NS not in text
    assert SECRET_SUBJ not in text


def test_get_subject_access_log_hides_path_values(client, register, caplog):
    assert register(client, SECRET_NS, SECRET_SUBJ, make_image(seed=72)).status_code == 201
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        resp = client.get(f"/v1/namespaces/{SECRET_NS}/subjects/{SECRET_SUBJ}")
    assert resp.status_code == 200
    text = _access_text(caplog)
    assert "/v1/namespaces/{namespace}/subjects/{subject_id}" in text
    assert SECRET_NS not in text
    assert SECRET_SUBJ not in text


def test_delete_subject_access_log_hides_path_values(client, register, caplog):
    assert register(client, SECRET_NS, SECRET_SUBJ, make_image(seed=73)).status_code == 201
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        resp = client.delete(f"/v1/namespaces/{SECRET_NS}/subjects/{SECRET_SUBJ}")
    assert resp.status_code == 200
    text = _access_text(caplog)
    assert "/v1/namespaces/{namespace}/subjects/{subject_id}" in text
    assert SECRET_NS not in text
    assert SECRET_SUBJ not in text


def test_unmatched_path_fallback_keeps_only_two_segments(client, caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        resp = client.get(f"/v1/namespaces/{SECRET_NS}/totally-unknown")
    assert resp.status_code == 404
    text = _access_text(caplog)
    assert SECRET_NS not in text
    assert "/v1/namespaces" in text


def test_no_image_bytes_or_token_in_access_log(client, extract, caplog):
    image = make_image(seed=74)
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        resp = extract(client, image, namespace=SECRET_NS)
    assert resp.status_code == 200
    text = _access_text(caplog)
    assert "embedding" not in text
    # Raw image bytes must never be logged.
    assert image[:16].hex() not in text


def test_search_access_log_uses_template_and_hides_values(client, register, caplog):
    image = make_image(seed=75)
    assert register(client, SECRET_NS, SECRET_SUBJ, image).status_code == 201
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        resp = client.post(
            f"/v1/namespaces/{SECRET_NS}/search",
            files={"image": ("f.png", image, "image/png")},
        )
    assert resp.status_code == 200
    text = _access_text(caplog)
    # Route template only -- no expanded path, no identity values, no bytes.
    assert "/v1/namespaces/{namespace}/search" in text
    assert SECRET_NS not in text
    assert SECRET_SUBJ not in text
    assert "embedding" not in text
    assert image[:16].hex() not in text
