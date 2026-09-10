"""领取（claim）：一个短事务内 SELECT ... FOR UPDATE SKIP LOCKED + 条件 UPDATE，
提交后才允许做 handler/外部调用（DD 9.2、ARCH 8.2）。

只锁 T12 行本身，立即提交；绝不持 T12 等业务行（DD 8.1）。

重试上限（oracle M7）：领取条件必须 `attempt_count < max_attempts`——
到期重排队/过期回收回来的任务若已达上限，不再被领取，只能由恢复器
（expire.recover_expired）落终态 failed，杜绝"崩溃→租约过期→再领取"
循环突破 max_attempts。
"""
from __future__ import annotations

from sqlalchemy import Engine, text

from .rows import JobRow

_SELECT_CLAIMABLE = text(
    """
SELECT id, job_type, owner_type, owner_id, input_revision, dedup_key, payload,
       attempt_count, max_attempts, lease_revision
FROM async_jobs
WHERE status = 'queued' AND available_at <= CURRENT_TIMESTAMP
  AND attempt_count < max_attempts
ORDER BY available_at, id
LIMIT :batch
FOR UPDATE SKIP LOCKED
"""
)

# 单表条件更新（batch 内逐行；行锁已在同一事务持有）。RETURNING 取新代次值。
_MARK_RUNNING = text(
    """
UPDATE async_jobs
SET status = 'running',
    lease_owner = :worker_id,
    lease_until = CURRENT_TIMESTAMP + make_interval(secs => :lease_seconds),
    lease_revision = lease_revision + 1,
    attempt_count = attempt_count + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id AND status = 'queued'
RETURNING lease_revision, attempt_count
"""
)


def claim_batch(
    engine: Engine,
    *,
    worker_id: str,
    lease_seconds: int,
    batch_size: int,
) -> list[JobRow]:
    """领取一批到期 queued 任务并置为 running（新租约代次）。

    两个并发领取者经 SKIP LOCKED 永不拿到同一行；返回行携带 UPDATE 后的
    新 lease_revision / attempt_count。
    """
    claimed: list[JobRow] = []
    with engine.begin() as conn:
        rows = conn.execute(_SELECT_CLAIMABLE, {"batch": batch_size}).mappings().all()
        for row in rows:
            upd = conn.execute(
                _MARK_RUNNING,
                {
                    "worker_id": worker_id,
                    "lease_seconds": int(lease_seconds),
                    "id": row["id"],
                },
            ).mappings().one()
            claimed.append(
                JobRow(
                    id=str(row["id"]),
                    job_type=row["job_type"],
                    owner_type=row["owner_type"],
                    owner_id=str(row["owner_id"]),
                    input_revision=int(row["input_revision"]),
                    dedup_key=row["dedup_key"],
                    payload=dict(row["payload"]),
                    attempt_count=int(upd["attempt_count"]),
                    max_attempts=int(row["max_attempts"]),
                    lease_revision=int(upd["lease_revision"]),
                    lease_owner=worker_id,
                )
            )
    return claimed
