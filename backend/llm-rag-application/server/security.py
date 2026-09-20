"""API key authentication for FastAPI business routes.

Design goals
------------
* **One dependency, many routes.** ``verify_api_key`` is attached via
  ``dependencies=[Depends(verify_api_key)]`` at the *route-registration* layer,
  so the handler signatures (``create_knowledge_base``, ``knowledge_base_chat`` …)
  never change. All policy lives here.
* **Fail-closed.** When ``auth_enabled`` is ``True`` but no key is configured,
  the service refuses traffic with 503 instead of silently allowing everyone in.
* **Constant-time comparison.** ``secrets.compare_digest`` prevents timing attacks
  that could brute-force the shared key.
* **Separate credentials.** ``X-API-Key`` identifies the trusted application;
  ``Authorization: Bearer`` is reserved for the end-user access token.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from rag.common.configuration import settings
from rag.common.utils import logger

# ``auto_error=False`` lets us produce a uniform 401 body instead of FastAPI's
# default 403 when the header is absent.
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
def verify_api_key(
    request: Request,
    x_api_key: str | None = Depends(_API_KEY_HEADER),
) -> str | None:
    """Dependency that gates business endpoints behind a shared API key.

    When ``settings.server.auth_enabled`` is ``False`` this service-credential
    check is skipped, but user access-token validation still applies. When
    enabled, every request must carry a key matching ``settings.server.auth_key``.

    :returns: The validated key (or ``None`` when auth is disabled) so handlers
        that need caller identity can reuse ``Depends(verify_api_key)``.
    :raises HTTPException: 401 for a missing/wrong key, 503 for misconfiguration.
    """
    server = settings.server
    if not server.auth_enabled:
        return None

    expected = (server.auth_key or "").strip()
    if not expected:
        logger.error(
            "Authentication is enabled but auth_key is empty; "
            "refusing all traffic. Set APP_SERVER_AUTH_KEY."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication misconfigured.",
        )

    provided = x_api_key.strip() if x_api_key and x_api_key.strip() else None
    if not provided or not secrets.compare_digest(provided, expected):
        logger.warning(
            "Rejected %s %s: %s",
            request.method,
            request.url.path,
            "no API key provided" if not provided else "invalid API key",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
    return provided
