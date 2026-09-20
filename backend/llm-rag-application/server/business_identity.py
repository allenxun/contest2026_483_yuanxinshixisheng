from dataclasses import dataclass

from fastapi import HTTPException, status

from rag.business.registry import business_registry
from server.identity import Principal


@dataclass(frozen=True)
class BusinessIdentity:
    business_type: str
    organization_id: str | None = None


def resolve_business_identity(
    principal: Principal,
    requested_business_type: str,
) -> BusinessIdentity:
    """Resolve a business identity from trusted profile claims, never prompt text."""
    business_type = (requested_business_type or "customer").strip().lower()
    if business_type not in business_registry.names():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported business identity.",
        )
    if business_type not in principal.business_types and not principal.has_any_role({"admin"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The requested business identity is not assigned to this user.",
        )
    return BusinessIdentity(
        business_type=business_type,
        organization_id=principal.organization_id,
    )
