"""Worker 侧 T12 入队助手（去重语义 + 部分唯一索引冲突区分）。

- ``insert_job`` 在调用方事务内执行（供 business_tx 与后继任务同事务提交）；
- ``enqueue_job`` 自开短事务（供跨事务阶段，如 identity.enroll 触发）；
- ``enqueue_identity_enroll`` 额外把 ``uq_job_identity_enroll`` 冲突翻译为
  :class:`EnrollSlotOccupied`（namespace 级未决登记占满 → 候选等待重搜）。

payload 一律 dict 且 ``schema_version`` 必须为 JSON 整数（T12 CHECK 要求 object 且
``schema_version`` 为 number）。
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from ...config import WorkerConfig

_INSERT_JOB = text(
    """
INSERT INTO async_jobs (id, job_type, dedup_key, owner_type, owner_id, input_revision,
                        payload, status, available_at, attempt_count, max_attempts,
                        lease_revision, created_at, updated_at)
VALUES (gen_random_uuid(), :job_type, :dedup_key, :owner_type, CAST(:owner_id AS uuid),
        :input_revision, CAST(:payload AS jsonb), 'queued',
        CURRENT_TIMESTAMP + make_interval(secs => :delay_seconds),
        0, :max_attempts, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (dedup_key) DO NOTHING
RETURNING id
"""
)

_SELECT_BY_DEDUP = text("SELECT id FROM async_jobs WHERE dedup_key = :dedup_key")


class EnrollSlotOccupied(RuntimeError):
    """namespace 级 identity.enroll 未决槽已被占用（uq_job_identity_enroll）。"""


def _is_enroll_slot_conflict(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None) if diag is not None else None
    if name == "uq_job_identity_enroll":
        return True
    return "uq_job_identity_enroll" in str(exc)


def insert_job(
    conn: Connection,
    *,
    job_type: str,
    dedup_key: str,
    owner_type: str,
    owner_id: str,
    input_revision: int,
    payload: dict[str, Any],
    available_at_delay_seconds: float = 0.0,
    max_attempts: Optional[int] = None,
) -> tuple[str, bool]:
    """在调用方事务内插入（或按 dedup_key 复用）一行 queued 任务。

    返回 ``(job_id, replayed)``：dedup 冲突 = 同一逻辑任务重放（不是错误）。
    可能向上抛 ``IntegrityError``（如 identity 部分唯一索引）；调用方决定语义。
    """
    if not isinstance(payload, dict):
        raise ValueError("job payload must be a JSON object")
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ValueError("job payload must carry an integer schema_version")
    attempts = max_attempts if max_attempts is not None else WorkerConfig().retry_max_attempts
    row = conn.execute(
        _INSERT_JOB,
        {
            "job_type": job_type,
            "dedup_key": dedup_key,
            "owner_type": owner_type,
            "owner_id": owner_id,
            "input_revision": int(input_revision),
            "payload": json.dumps(payload, ensure_ascii=False),
            "delay_seconds": float(available_at_delay_seconds),
            "max_attempts": int(attempts),
        },
    ).first()
    if row is None:
        existing = conn.execute(_SELECT_BY_DEDUP, {"dedup_key": dedup_key}).first()
        if existing is None:  # pragma: no cover - 仅理论竞态
            raise RuntimeError(f"dedup conflict without existing row: {dedup_key}")
        return str(existing[0]), True
    return str(row[0]), False


def enqueue_job(
    engine: Engine,
    *,
    job_type: str,
    dedup_key: str,
    owner_type: str,
    owner_id: str,
    input_revision: int,
    payload: dict[str, Any],
    available_at_delay_seconds: float = 0.0,
    max_attempts: Optional[int] = None,
) -> tuple[str, bool]:
    """自开短事务入队（提交后才返回）。"""
    with engine.begin() as conn:
        return insert_job(
            conn,
            job_type=job_type,
            dedup_key=dedup_key,
            owner_type=owner_type,
            owner_id=owner_id,
            input_revision=input_revision,
            payload=payload,
            available_at_delay_seconds=available_at_delay_seconds,
            max_attempts=max_attempts,
        )


def enqueue_identity_enroll(
    engine: Engine, **kwargs: Any
) -> tuple[str, bool]:
    """入队 identity.enroll；namespace 未决槽占用 → :class:`EnrollSlotOccupied`。

    索引冲突发生在本助手自开的短事务内，异常时事务已回滚，不会悬挂部分写。
    """
    try:
        with engine.begin() as conn:
            return insert_job(conn, **kwargs)
    except IntegrityError as exc:
        if _is_enroll_slot_conflict(exc):
            raise EnrollSlotOccupied("identity enrollment slot occupied") from exc
        raise
