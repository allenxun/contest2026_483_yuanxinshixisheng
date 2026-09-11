"""会话有效性核实探针（锁外的第 3 步）。

真实会话提供方未选定 → dev/test 以 **DB 事实**核实：T09 行存在、``status='active'``、
``account_id``/``destination_revision`` 与 T10 快照一致，并返回锁外读到的
**会话快照**（``session_ref``/``destination_revision``/``account_id``/``status``）。
handler 把该快照带进加锁后的短事务逐项复核，以封堵"锁外核验之后、加锁之前"
目标被并发改写（会话/代次/账号漂移）的 TOCTOU 窗口。查询失败（异常/不可用）
由 handler 视为"未核实 → 不投递"（可重试）。

探针返回 ``None`` 表示**否定**（目标不存在 / 不可见 / 非 active / 代次不符）；
绝不返回布尔结论。生产 fail-closed：无真实探针 → :func:`build_session_probe`
抛错，绝不默认放行。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .config import NotificationSettings


@dataclass(frozen=True)
class SessionSnapshot:
    """锁外核验通过时读到的 T09 事实快照（带入锁内逐项复核）。"""

    session_ref: Optional[str]
    destination_revision: int
    account_id: str
    status: str


@runtime_checkable
class SessionVerifier(Protocol):
    def verify(
        self,
        *,
        account_id: str,
        destination_id: str,
        destination_revision: int,
    ) -> Optional[SessionSnapshot]: ...


class DevDbSessionProbe:
    """dev/test 替身：只读单表 T09 核实会话/目标快照仍一致，并返回该快照。"""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def verify(
        self,
        *,
        account_id: str,
        destination_id: str,
        destination_revision: int,
    ) -> Optional[SessionSnapshot]:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT session_ref, destination_revision, account_id, status"
                    " FROM notification_destinations"
                    " WHERE id = :did AND account_id = :acct"
                    " AND destination_revision = :rev"
                    " AND status = 'active'"
                ),
                {
                    "did": destination_id,
                    "acct": account_id,
                    "rev": destination_revision,
                },
            ).mappings().first()
        if row is None:
            return None
        return SessionSnapshot(
            session_ref=row["session_ref"],
            destination_revision=int(row["destination_revision"]),
            account_id=str(row["account_id"]),
            status=row["status"],
        )


def build_session_probe(engine: Engine, settings: NotificationSettings) -> SessionVerifier:
    if settings.production:
        raise RuntimeError(
            "no real session provider configured for production; refusing to deliver (fail closed)"
        )
    return DevDbSessionProbe(engine)
