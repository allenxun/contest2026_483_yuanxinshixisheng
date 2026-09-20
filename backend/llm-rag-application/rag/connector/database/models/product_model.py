from sqlalchemy import (
    BigInteger,
    Column,
    Index,
    Text,
    String,
    DateTime,
    func,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP

from rag.connector.database.base import Base


class CosmeticProductModel(Base):
    """NMPA cosmetic product registration / filing record."""

    __tablename__ = "cosmetic_product"
    __table_args__ = (
        Index("ix_cosmetic_regulatory_number", "regulatory_number"),
        Index("ix_cosmetic_source_id", "source_id"),
        Index("ix_cosmetic_status", "status"),
        Index("ix_cosmetic_domestic_or_imported", "domestic_or_imported"),
        Index("ix_cosmetic_ordinary_or_special", "ordinary_or_special"),
        Index(
            "ix_cosmetic_product_name_trgm",
            "product_name",
            postgresql_using="gin",
            postgresql_ops={"product_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_cosmetic_registrant_trgm",
            "registrant_or_filer",
            postgresql_using="gin",
            postgresql_ops={"registrant_or_filer": "gin_trgm_ops"},
        ),
        Index(
            "ix_cosmetic_manufacturer_trgm",
            "manufacturer",
            postgresql_using="gin",
            postgresql_ops={"manufacturer": "gin_trgm_ops"},
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    internal_record_key = Column(String(64), nullable=False, unique=True, index=True)
    source_id = Column(String(100), nullable=False)
    record_type = Column(String(100))
    regulatory_number = Column(String(100))
    product_name = Column(Text)
    domestic_or_imported = Column(String(20))
    ordinary_or_special = Column(String(20))
    registrant_or_filer = Column(Text)
    domestic_responsible_person = Column(Text)
    manufacturer = Column(Text)
    production_address = Column(Text)
    product_category = Column(String(255))
    use_area = Column(Text)
    efficacy_claims = Column(Text)
    ingredients = Column(Text)
    registration_or_filing_date = Column(String(50))
    valid_until = Column(String(50))
    status = Column(String(100))
    label_url = Column(Text)
    standard_url = Column(Text)
    efficacy_summary_url = Column(Text)
    source_url = Column(Text)
    retrieved_at = Column(TIMESTAMP(timezone=True), nullable=True)
    raw_file = Column(Text)
    skin_scope_status = Column(String(50))
    skin_scope_reason = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DrugProductModel(Base):
    """NMPA drug product approval record."""

    __tablename__ = "drug_product"
    __table_args__ = (
        Index("ix_drug_approval_number", "approval_number"),
        Index("ix_drug_original_approval_number", "original_approval_number"),
        Index("ix_drug_source_id", "source_id"),
        Index("ix_drug_status", "status"),
        Index("ix_drug_domestic_or_imported", "domestic_or_imported"),
        Index(
            "ix_drug_generic_name_trgm",
            "generic_name",
            postgresql_using="gin",
            postgresql_ops={"generic_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_drug_trade_name_trgm",
            "trade_name",
            postgresql_using="gin",
            postgresql_ops={"trade_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_drug_manufacturer_trgm",
            "manufacturer",
            postgresql_using="gin",
            postgresql_ops={"manufacturer": "gin_trgm_ops"},
        ),
        Index(
            "ix_drug_mah_trgm",
            "marketing_authorization_holder",
            postgresql_using="gin",
            postgresql_ops={"marketing_authorization_holder": "gin_trgm_ops"},
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    internal_record_key = Column(String(64), nullable=False, unique=True, index=True)
    source_id = Column(String(100), nullable=False)
    record_type = Column(String(100))
    approval_number = Column(String(100))
    original_approval_number = Column(String(100))
    generic_name = Column(Text)
    trade_name = Column(Text)
    domestic_or_imported = Column(String(20))
    drug_category = Column(String(255))
    dosage_form = Column(String(255))
    specification = Column(Text)
    marketing_authorization_holder = Column(Text)
    manufacturer = Column(Text)
    production_address = Column(Text)
    approval_date = Column(String(50))
    valid_until = Column(String(50))
    indications = Column(Text)
    instructions_url = Column(Text)
    review_report_url = Column(Text)
    status = Column(String(100))
    source_url = Column(Text)
    retrieved_at = Column(TIMESTAMP(timezone=True), nullable=True)
    raw_file = Column(Text)
    skin_scope_status = Column(String(50))
    skin_scope_reason = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )
