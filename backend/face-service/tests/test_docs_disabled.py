"""Auth-surface convergence: the interactive docs surfaces are disabled.

FastAPI exposes ``/docs``, ``/redoc`` and ``/openapi.json`` by default, none of
which sit behind the internal-token dependency.  This service only talks to the
Java adapter, so all three must be 404.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_surfaces_are_404(client, path):
    resp = client.get(path)
    assert resp.status_code == 404, f"{path} must not be served"


def test_openapi_schema_is_not_reachable(client):
    # A JSON schema body must never be returned at any of the three paths.
    for path in ("/docs", "/redoc", "/openapi.json"):
        resp = client.get(path)
        assert "openapi" not in resp.text.lower()
        assert "swagger" not in resp.text.lower()