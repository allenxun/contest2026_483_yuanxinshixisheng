"""完成/失败写回：短事务 + 代次守卫（DD 8.1 锁顺序：先业务行后 T12）。

- complete_success：同一事务内 **先** 执行 handler 的业务写回调（B/C/D 扩展点，
  echo 为空），**后** 条件更新 async_jobs → succeeded；守卫 0 行 → StaleGeneration，
  整个事务回滚（业务写不得发布）。守卫含**真实执行时刻**的租约未过期检查
  （``clock_timestamp()``）：回调耗尽租约时成功写回同样被拒绝 → 回收器重排 →
  新 owner 依 revision/dedup 守卫重做（handler 幂等）。
- complete_failure：可重试且未超上限 → 回 queued + 指数退避 available_at +
  last_error；否则 failed。可选 ``business_tx`` 在同一事务内**先**执行终态业务写、
  再守卫 UPDATE（含租约未过期），0 行 → StaleGeneration 整体回滚；无 callback 调用方
  行为不变。守卫同代次。
- fail_unsupported：未知 job_type / 未注册 handler / payload schema_version
  不符 / JSON Schema 校验失败 → 直接 failed（UNSUPPORTED_CONTRACT），不重试、
  不循环（DD 9.1）。

last_error JSON（snake_case）：{"code","message","retryable","retry_after_seconds"?}。
"""
from __future__ import annotations

import json
import random
from typing import Any, Callable, Optional

from sqlalchemy import Connection, Engine, text

from .rows import JobRow


class StaleGeneration(RuntimeError):
    """lease_owner/lease_revision/status 守卫不匹配：结果作废，事务已回滚。"""


BusinessTx = Callable[[Connection], None]

_COMPLETE_SUCCESS = text(
    """
UPDATE async_jobs
SET status = 'succeeded',
    finished_at = CURRENT_TIMESTAMP,
    last_error = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id AND status = 'running'
  AND lease_owner = :worker_id AND lease_revision = :lease_revision
  AND lease_until >= clock_timestamp()
"""
)

_REQUEUE = text(
    """
UPDATE async_jobs
SET status = 'queued',
    lease_owner = NULL,
    lease_until = NULL,
    available_at = CURRENT_TIMESTAMP + make_interval(secs => :delay_seconds),
    last_error = CAST(:last_error AS jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id AND status = 'running'
  AND lease_owner = :worker_id AND lease_revision = :lease_revision
  AND lease_until >= clock_timestamp()
"""
)

_MARK_FAILED = text(
    """
UPDATE async_jobs
SET status = 'failed',
    finished_at = CURRENT_TIMESTAMP,
    last_error = CAST(:last_error AS jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id AND status = 'running'
  AND lease_owner = :worker_id AND lease_revision = :lease_revision
  AND lease_until >= clock_timestamp()
"""
)

# 合法等待态重排（defer）：同 job、同 dedup_key/input_revision；退还本次 claim
# 的 attempt 增量（GREATEST 防负），lease_revision+1 作废旧领取代次，available_at
# 推到下次检查时刻。**绝不写/读 last_error**（诊断字段不得驱动决策）。
# 租约校验用 clock_timestamp()（真实语句执行时刻，非事务起始 CURRENT_TIMESTAMP）：
# business_tx 先于守卫执行，若回调耗尽租约，守卫必须在此刻判定过期 → StaleGeneration
# → 业务与重排整体回滚（过期领取者绝不提交结果）。
_DEFER = text(
    """
UPDATE async_jobs
SET status = 'queued',
    lease_owner = NULL,
    lease_until = NULL,
    available_at = CURRENT_TIMESTAMP + make_interval(secs => :defer_seconds),
    attempt_count = GREATEST(attempt_count - 1, 0),
    lease_revision = lease_revision + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id AND status = 'running'
  AND lease_owner = :worker_id AND lease_revision = :lease_revision
  AND lease_until >= clock_timestamp()
"""
)


def backoff_seconds(
    attempt_count: int,
    *,
    base_seconds: int,
    cap_seconds: int,
    rng: Optional[random.Random] = None,
) -> int:
    """指数退避 + 抖动：delay = min(base * 2^(attempt-1), cap) + U(0, 0.2*delay)。

    attempt_count 为本次已消耗的尝试数（claim 时递增，最小 1）。
    dev 初值 5s→300s（decisions #13）。
    """
    r = rng or random
    exp = min(float(base_seconds) * (2 ** max(int(attempt_count) - 1, 0)), float(cap_seconds))
    return int(round(exp + r.uniform(0.0, 0.2 * exp)))


def make_last_error(
    code: str, message: str, *, retryable: bool, retry_after_seconds: Optional[int] = None
) -> str:
    err: dict[str, Any] = {
        "code": code,
        "message": message[:2000],
        "retryable": retryable,
    }
    if retry_after_seconds is not None:
        err["retry_after_seconds"] = int(retry_after_seconds)
    return json.dumps(err, ensure_ascii=False)


def complete_success(
    engine: Engine,
    claim: JobRow,
    *,
    handler_result_tx: Optional[BusinessTx] = None,
) -> None:
    """成功路径单事务：业务写 → T12 succeeded（守卫不满足则全部回滚）。

    守卫含 ``lease_until >= clock_timestamp()``：成功提交同样要求**真实执行时刻**
    租约仍活跃。回调先于守卫执行，若回调耗时耗尽租约，成功（业务写 + succeeded）
    被拒绝 → StaleGeneration → 整体回滚 → 回收器重排 → 新 owner 依 revision/dedup
    守卫重做（handler 幂等，故重做安全）。
    """
    with engine.begin() as conn:
        if handler_result_tx is not None:
            # 扩展点：B/C/D 在此写业务表（字段级、先锁业务行）；echo 无业务写
            handler_result_tx(conn)
        res = conn.execute(
            _COMPLETE_SUCCESS,
            {
                "id": claim.id,
                "worker_id": claim.lease_owner,
                "lease_revision": claim.lease_revision,
            },
        )
        if res.rowcount == 0:
            # 代次失效：连同业务写一起回滚，结果不得发布
            raise StaleGeneration(
                f"job {claim.id} stale generation on complete (revision={claim.lease_revision})"
            )


def complete_deferred(
    engine: Engine,
    claim: JobRow,
    *,
    defer_seconds: float,
    business_tx: Optional[BusinessTx] = None,
) -> None:
    """合法等待态重排（defer）单事务：业务守卫 → 代次围栏回 queued。

    **仅用于合法等待态**（如能力待补齐）：同一 job、同一 ``dedup_key``/
    ``input_revision``，不产生后继任务；退还**本次 claim** 的 attempt 增量
    （``attempt_count = GREATEST(attempt_count - 1, 0)``，永不为负），
    ``lease_revision + 1`` 让旧领取代次失效，``available_at`` 推到
    ``now + defer_seconds``。绝不触碰业务 generation revision。

    真实算法/网络失败**必须**走 :func:`complete_failure` 并消耗 attempt 预算，
    不得用本函数掩盖失败。

    ``business_tx`` 若给定，先在**同一连接/事务**执行（先锁业务行，DD 8.1）：
    调用方用它复核业务输入仍是本任务输入版本（不一致抛
    :class:`StaleGeneration`），并可写入合法等待态；抛出即整体回滚。

    守卫 0 行（陈旧租约 / 重复 defer / 租约已过期）→ :class:`StaleGeneration`，
    事务已回滚：无 refund、无状态变更、无双重退款。本函数**不写也不读**
    ``last_error``（诊断字段不得驱动决策）。
    """
    with engine.begin() as conn:
        if business_tx is not None:
            business_tx(conn)
        res = conn.execute(
            _DEFER,
            {
                "id": claim.id,
                "worker_id": claim.lease_owner,
                "lease_revision": claim.lease_revision,
                "defer_seconds": float(defer_seconds),
            },
        )
        if res.rowcount == 0:
            raise StaleGeneration(
                f"job {claim.id} stale generation on defer (revision={claim.lease_revision})"
            )


def complete_failure(
    engine: Engine,
    claim: JobRow,
    *,
    code: str,
    message: str,
    retryable: bool,
    backoff_base_seconds: int = 5,
    backoff_cap_seconds: int = 300,
    business_tx: Optional[BusinessTx] = None,
) -> None:
    """失败路径：可重试且未超 attempt 上限 → 退避回 queued；否则 failed。

    ``business_tx`` 可选：在**同一事务**内先执行终态业务写（禁网络），再做守卫
    UPDATE（failed/requeue 两路径均校验 status/owner/lease_revision/租约未过期）；
    守卫 0 行 → :class:`StaleGeneration`，业务写与任务状态**整体回滚**。这样
    「业务终态」与「T12 终态」原子提交，杜绝崩溃窗口导致的审计不一致（oracle N2）。
    无 callback 的调用方（A echo / B 通知）行为不变。

    租约过期用 ``clock_timestamp()``（真实执行时刻）判定，而非事务起始的
    ``CURRENT_TIMESTAMP``：回调先于守卫执行，若回调耗时耗尽租约，守卫在此刻判过期
    → StaleGeneration → 业务+任务写**整体回滚**（过期领取者绝不提交业务结果）。

    0 行守卫 → StaleGeneration（调用方记日志丢弃即可：回收器会重新入队）。
    """
    will_retry = retryable and claim.attempt_count < claim.max_attempts
    if will_retry:
        delay = backoff_seconds(
            claim.attempt_count,
            base_seconds=backoff_base_seconds,
            cap_seconds=backoff_cap_seconds,
        )
        last_error = make_last_error(
            code, message, retryable=True, retry_after_seconds=delay
        )
        stmt = _REQUEUE
        params: dict[str, Any] = {"delay_seconds": delay}
    else:
        last_error = make_last_error(code, message, retryable=False)
        stmt = _MARK_FAILED
        params = {}
    params.update(
        {
            "id": claim.id,
            "worker_id": claim.lease_owner,
            "lease_revision": claim.lease_revision,
            "last_error": last_error,
        }
    )
    with engine.begin() as conn:
        if business_tx is not None:
            # 同事务先执行业务写（禁网络）；随后守卫 0 行则连业务写一起回滚
            business_tx(conn)
        res = conn.execute(stmt, params)
        if res.rowcount == 0:
            raise StaleGeneration(
                f"job {claim.id} stale generation on failure write (revision={claim.lease_revision})"
            )


def fail_unsupported(
    engine: Engine,
    claim: JobRow,
    *,
    reason_code: str = "UNSUPPORTED_CONTRACT",
    message: str = "unsupported contract: no registered handler or payload schema mismatch",
) -> None:
    """契约不认识 → 立即 failed（retryable=false），绝不进入重试循环。"""
    last_error = make_last_error(reason_code, message, retryable=False)
    with engine.begin() as conn:
        res = conn.execute(
            _MARK_FAILED,
            {
                "id": claim.id,
                "worker_id": claim.lease_owner,
                "lease_revision": claim.lease_revision,
                "last_error": last_error,
            },
        )
        if res.rowcount == 0:
            raise StaleGeneration(
                f"job {claim.id} stale generation on unsupported (revision={claim.lease_revision})"
            )
