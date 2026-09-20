"""Structured queries for cosmetic and drug product tables."""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select, text

from rag.connector.database.base import SessionLocal
from rag.connector.database.models.product_model import (
    CosmeticProductModel,
    DrugProductModel,
)

_MAX_LIMIT = 50
_DEFAULT_LIMIT = 10


def _clamp_limit(value: int) -> int:
    if value < 1:
        return 1
    if value > _MAX_LIMIT:
        return _MAX_LIMIT
    return value


def _to_dict(record: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    return {col: getattr(record, col, None) for col in columns}


def _cosmetic_columns() -> tuple[str, ...]:
    return tuple(c.name for c in CosmeticProductModel.__table__.columns)


def _drug_columns() -> tuple[str, ...]:
    return tuple(c.name for c in DrugProductModel.__table__.columns)


def search_cosmetics(
    *,
    query: str | None = None,
    regulatory_number: str | None = None,
    manufacturer: str | None = None,
    status: str | None = None,
    domestic_or_imported: str | None = None,
    ordinary_or_special: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Search cosmetic_product with structured filters.

    Raises ValueError when no query condition is provided.
    """
    has_condition = any([
        query, regulatory_number, manufacturer, status,
        domestic_or_imported, ordinary_or_special,
    ])
    if not has_condition:
        raise ValueError("至少需要一个查询条件")

    limit = _clamp_limit(limit)
    stmt = select(CosmeticProductModel)

    # Regulatory number: exact match.
    if regulatory_number:
        stmt = stmt.where(CosmeticProductModel.regulatory_number == regulatory_number)

    # Name keyword: ILIKE across product_name, registrant_or_filer, manufacturer.
    if query:
        pattern = f"%{query}%"
        name_filter = or_(
            CosmeticProductModel.product_name.ilike(pattern),
            CosmeticProductModel.registrant_or_filer.ilike(pattern),
            CosmeticProductModel.manufacturer.ilike(pattern),
        )
        stmt = stmt.where(name_filter)

    if manufacturer:
        stmt = stmt.where(CosmeticProductModel.manufacturer.ilike(f"%{manufacturer}%"))
    if status:
        stmt = stmt.where(CosmeticProductModel.status == status)
    if domestic_or_imported:
        stmt = stmt.where(CosmeticProductModel.domestic_or_imported == domestic_or_imported)
    if ordinary_or_special:
        stmt = stmt.where(CosmeticProductModel.ordinary_or_special == ordinary_or_special)

    # Stable sort: exact regulatory_number > exact product_name > prefix > contains > id.
    if regulatory_number:
        stmt = stmt.order_by(
            CosmeticProductModel.regulatory_number == regulatory_number,
            CosmeticProductModel.id,
        )
    elif query:
        stmt = stmt.order_by(
            CosmeticProductModel.product_name == query,
            CosmeticProductModel.product_name.ilike(f"{query}%"),
            CosmeticProductModel.product_name.ilike(f"%{query}%"),
            CosmeticProductModel.id,
        )
    else:
        stmt = stmt.order_by(CosmeticProductModel.id)

    stmt = stmt.offset(offset).limit(limit)

    cols = _cosmetic_columns()
    with SessionLocal() as session:
        rows = session.execute(stmt).scalars().all()
        return [_to_dict(row, cols) for row in rows]


def search_drugs(
    *,
    query: str | None = None,
    approval_number: str | None = None,
    manufacturer: str | None = None,
    status: str | None = None,
    domestic_or_imported: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Search drug_product with structured filters.

    Raises ValueError when no query condition is provided.
    """
    has_condition = any([
        query, approval_number, manufacturer, status, domestic_or_imported,
    ])
    if not has_condition:
        raise ValueError("至少需要一个查询条件")

    limit = _clamp_limit(limit)
    stmt = select(DrugProductModel)

    if approval_number:
        stmt = stmt.where(DrugProductModel.approval_number == approval_number)

    if query:
        pattern = f"%{query}%"
        name_filter = or_(
            DrugProductModel.generic_name.ilike(pattern),
            DrugProductModel.trade_name.ilike(pattern),
            DrugProductModel.manufacturer.ilike(pattern),
            DrugProductModel.marketing_authorization_holder.ilike(pattern),
        )
        stmt = stmt.where(name_filter)

    if manufacturer:
        stmt = stmt.where(DrugProductModel.manufacturer.ilike(f"%{manufacturer}%"))
    if status:
        stmt = stmt.where(DrugProductModel.status == status)
    if domestic_or_imported:
        stmt = stmt.where(DrugProductModel.domestic_or_imported == domestic_or_imported)

    if approval_number:
        stmt = stmt.order_by(
            DrugProductModel.approval_number == approval_number,
            DrugProductModel.id,
        )
    elif query:
        stmt = stmt.order_by(
            DrugProductModel.generic_name == query,
            DrugProductModel.generic_name.ilike(f"{query}%"),
            DrugProductModel.generic_name.ilike(f"%{query}%"),
            DrugProductModel.id,
        )
    else:
        stmt = stmt.order_by(DrugProductModel.id)

    stmt = stmt.offset(offset).limit(limit)

    cols = _drug_columns()
    with SessionLocal() as session:
        rows = session.execute(stmt).scalars().all()
        return [_to_dict(row, cols) for row in rows]
