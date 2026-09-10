"""过期回收（recovery）与优雅停机释放。

回收器用条件更新把租约过期的 running 任务转回 queued 并递增 lease_revision，
使旧领取者的代次整体失效——绝不"只查时间后无条件覆盖新领取者"（DD 9.2）。
available_at 不改（失败重试路径已按退避设置过）。

重试上限（oracle M7）：回收时若 `attempt_count >= max_attempts`（崩溃/超时
循环已耗尽预算），不再重排队，改条件更新落终态 failed + RETRY_LIMIT_EXCEEDED
last_error；否则旧领取者过期后任务被无限重放。两条 UPDATE 各自带
`status='running' AND lease_until < now` 代次守护，同一事务内先判定终态、
后回收仍有预算的行，互斥不重复计数。
"""
from __future__ import annotations

from sqlalchemy import Engine, text

from .rows import JobRow

# 已达上限：过期 running → failed 终态（RETRY_LIMIT_EXCEEDED），不再回队列。
_FAIL_AT_CEILING = text(
    """
UPDATE async_jobs
SET status = 'failed',
    finished_at = CURRENT_TIMESTAMP,
    lease_owner = NULL,
    lease_until = NULL,
    last_error = jsonb_build_object(
        'code', 'RETRY_LIMIT_EXCEEDED',
        'message', 'attempt ceiling reached via lease expiry; re-enroll needed for retry',
        'retryable', false),
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'running' AND lease_until < CURRENT_TIMESTAMP
  AND attempt_count >= max_attempts
RETURNING id
"""
)

# 仍有预算：过期 running → queued（代次 +1 使旧领取者失效）
_RECOVER_EXPIRED = text(
    """
UPDATE async_jobs
SET status = 'queued',
    lease_owner = NULL,
    lease_until = NULL,
    lease_revision = lease_revision + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'running' AND lease_until < CURRENT_TIMESTAMP
  AND attempt_count < max_attempts
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
  AND attempt_count < max_attempts
"""
)

# 优雅停机释放时已触顶：交还队列只会滞留（claim 条件不再领取），直接落 failed 终态。
_RELEASE_FAIL = text(
    """
UPDATE async_jobs
SET status = 'failed',
    finished_at = CURRENT_TIMESTAMP,
    lease_owner = NULL,
    lease_until = NULL,
    last_error = jsonb_build_object(
        'code', 'RETRY_LIMIT_EXCEEDED',
        'message', 'graceful release at attempt ceiling',
        'retryable', false),
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id AND status = 'running'
  AND lease_owner = :worker_id AND lease_revision = :lease_revision
  AND attempt_count >= max_attempts
"""
)


def recover_expired(engine: Engine) -> int:
    """回收所有租约过期任务：有预算→重排队（代次+1），触顶→failed 终态。

    返回处理条数（两者之和）。幂等条件更新，可任意频率运行（oracle M7）。
    """
    with engine.begin() as conn:
        failed = conn.execute(_FAIL_AT_CEILING).fetchall()
        requeued = conn.execute(_RECOVER_EXPIRED).fetchall()
    return len(requeued) + len(failed)


def release_claim(engine: Engine, claim: JobRow, *, worker_id: str) -> bool:
    """优雅停机 best-effort：仍持有当前代次时主动交还给 queued（代次递增，
    自身后续提交必然 StaleGeneration）；已触顶则落 failed 终态而非滞留队列。
    返回是否成功处理。"""
    with engine.begin() as conn:
        res = conn.execute(
            _RELEASE,
            {"id": claim.id, "worker_id": worker_id, "lease_revision": claim.lease_revision},
        )
        if res.rowcount > 0:
            return True
        res = conn.execute(
            _RELEASE_FAIL,
            {"id": claim.id, "worker_id": worker_id, "lease_revision": claim.lease_revision},
        )
    return res.rowcount > 0
