"""Access-token authentication and role-based access control (RBAC)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from fastapi import Depends, HTTPException, Request, status

from rag.common.configuration import settings
from rag.connector.database.repository.user_rights_repository import (
    get_business_identity,
)
from server.auth_client import AuthServiceClient, AuthServiceError
from server.security import verify_api_key


KNOWN_ROLES = frozenset({"user", "admin"})
KNOWN_BUSINESS_TYPES = frozenset({"customer", "advisor", "doctor"})
_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9@._:+-]{1,255}$")


@dataclass(frozen=True)
class Principal:
    """Authenticated application identity."""

    user_id: str
    roles: frozenset[str]
    source: str
    business_types: frozenset[str] = frozenset()
    organization_id: str | None = None

    def has_any_role(self, required_roles: Iterable[str]) -> bool:
        return bool(self.roles.intersection(required_roles))


def parse_roles(value: str) -> frozenset[str]:
    """Parse a comma-separated role claim and ignore unknown roles."""
    roles = {item.strip().lower() for item in (value or "").split(",") if item.strip()}
    return frozenset(roles.intersection(KNOWN_ROLES))


def parse_business_types(value) -> frozenset[str]:
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple, set, frozenset)):
        items = value
    else:
        items = ()
    parsed = {str(item).strip().lower() for item in items if str(item).strip()}
    return frozenset(parsed.intersection(KNOWN_BUSINESS_TYPES))


def principal_from_external_profile(
    profile: Mapping[str, Any],
    admin_user_ids: Iterable[str] = (),
    business_type: str | None = None,
) -> Principal:
    """Build a principal from a profile fetched server-side with its access token."""
    user_id = _validated_user_id(str(profile.get("user_id") or ""))
    raw_roles = profile.get("roles")
    if isinstance(raw_roles, str):
        roles = parse_roles(raw_roles)
    elif isinstance(raw_roles, (list, tuple, set, frozenset)):
        roles = parse_roles(",".join(str(role) for role in raw_roles))
    else:
        roles = frozenset()

    # Backward compatibility while the account service is rolling out roles.
    # A missing/empty role claim never grants elevated access.
    if not roles:
        roles = frozenset({"user"})
    if user_id in frozenset(str(item).strip() for item in admin_user_ids):
        roles = roles.union({"user", "admin"})
    business_types = parse_business_types(business_type)
    organization_id = str(profile.get("organization_id") or "").strip() or None
    return Principal(
        user_id,
        roles,
        "external_api",
        business_types,
        organization_id,
    )


def _validated_user_id(value: str) -> str:
    user_id = (value or "").strip()
    if not _USER_ID_PATTERN.fullmatch(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authenticated user identity.",
        )
    return user_id


def extract_bearer_token(authorization: str | None) -> str:
    """Extract a user access token from the standard Authorization header."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing user access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def get_current_principal(
    request: Request,
    _service_credential: str | None = Depends(verify_api_key),
) -> Principal:
    """Validate the end-user token server-side and build its trusted identity."""
    token = extract_bearer_token(request.headers.get("Authorization"))
    try:
        profile = AuthServiceClient(settings.auth_service).profile(token)
    except AuthServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.public_message,
            headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
        ) from exc
    user_id = _validated_user_id(str(profile.get("user_id") or ""))
    return principal_from_external_profile(
        profile,
        settings.server.get_admin_user_ids(),
        get_business_identity(user_id),
    )


def require_any_role(*required_roles: str):
    """Create a FastAPI dependency that enforces one of the supplied roles."""
    unknown = set(required_roles).difference(KNOWN_ROLES)
    if unknown:
        raise ValueError(f"Unknown application roles: {sorted(unknown)}")

    def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if not principal.has_any_role(required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return principal

    return dependency
