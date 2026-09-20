"""Optional internal bearer-token authentication.

The token is never logged and never echoed.  It is read once at startup from
either ``FACE_SVC_INTERNAL_TOKEN`` or a 0600 file referenced by
``FACE_SVC_INTERNAL_TOKEN_FILE``.  Comparison is constant-time.

When no token is configured the service is open *unless*
``FACE_SVC_AUTH_REQUIRED=true``, in which case startup fails instead of running
unprotected (enforced in :mod:`face_service.config`).
"""

from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import Request

from .config import ConfigError, Settings
from .errors import ErrorCode, FaceServiceError


class TokenAuth:
    def __init__(self, token: str | None, header_name: str = "X-Internal-Token") -> None:
        self._token = token
        self.header = header_name

    @classmethod
    def from_settings(cls, settings: Settings) -> "TokenAuth":
        token = settings.internal_token
        if token is None and settings.internal_token_file is not None:
            token = _read_token_file(settings.internal_token_file)
        return cls(token, settings.auth_header)

    @property
    def enabled(self) -> bool:
        return bool(self._token)

    def check(self, supplied: str | None) -> None:
        """Raise ``UNAUTHORIZED`` unless the supplied header is correct."""
        if not self.enabled:
            return
        if not supplied or not hmac.compare_digest(
            supplied.encode("utf-8"), self._token.encode("utf-8")  # type: ignore[union-attr]
        ):
            raise FaceServiceError(ErrorCode.UNAUTHORIZED)


def _read_token_file(path: Path) -> str:
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError("FACE_SVC_INTERNAL_TOKEN_FILE is not readable") from exc
    if not token:
        raise ConfigError("FACE_SVC_INTERNAL_TOKEN_FILE is empty")
    return token


def make_auth_dependency(auth: TokenAuth):
    """FastAPI dependency enforcing authentication for a route."""

    def _dependency(request: Request) -> None:
        auth.check(request.headers.get(auth.header))

    return _dependency


__all__ = ["TokenAuth", "make_auth_dependency"]
