"""过期回收（recovery）与优雅停机释放。

回收器用条件更新把租约过期的 running 任务转回 queued 并递增 lease_revision，
使旧领取者的代次整体失效——绝不"只查时间后无条件覆盖新领取者"（DD 9.2）。
available_at 不改（失败重试路径已按退避设置过）。
"""
from __future__ import annotations

from sqlalchemy import Engine, text

from .rows import JobRow

_RECOVER_EXPIRED = text(
    """
UPDATE async_jobs
SET status = 'queued',
    lease_owner = NULL,
    lease_until = NULL,
    lease_revision = lease_revision + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'running' AND lease_until < CURRENT_TIMESTAMP
RETURNING id
"""
)

_RELEASE = text(
    """
UPDATE async_jobs
SET status = 'queued',
    lease_owner = NULL,
    lease_until = NULL,
    lease_revision = lease_revision + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id AND status = 'running'
  AND lease_owner = :worker_id AND lease_revision = :lease_revision
"""
)


def recover_expired(engine: Engine) -> int:
    """回收所有租约过期任务，返回回收条数。幂等条件更新，可任意频率运行。"""
    with engine.begin() as conn:
        ids = conn.execute(_RECOVER_EXPIRED).fetchall()
    return len(ids)


def release_claim(engine: Engine, claim: JobRow, *, worker_id: str) -> bool:
    """优雅停机 best-effort：仍持有当前代次时主动交还给 queued（代次递增，
    自身后续提交必然 StaleGeneration）。返回是否成功释放。"""
    with engine.begin() as conn:
        res = conn.execute(
            _RELEASE,
            {"id": claim.id, "worker_id": worker_id, "lease_revision": claim.lease_revision},
        )
    return res.rowcount > 0
