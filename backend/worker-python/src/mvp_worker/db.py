"""SQLAlchemy Core 引擎工厂（psycopg 3 驱动，显式驱动名避免歧义）。"""
from __future__ import annotations

from sqlalchemy import Engine, create_engine, engine as _sa_engine
from sqlalchemy.engine import make_url


def create_db_engine(
    dsn: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 0,
) -> Engine:
    """按 DSN 建立独立短事务连接池（Web/Worker 各自独立池，事务不跨进程）。"""
    url = make_url(dsn)
    if url.drivername in ("postgresql", "postgres"):
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
    )
