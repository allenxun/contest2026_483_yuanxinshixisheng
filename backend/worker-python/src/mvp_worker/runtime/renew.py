"""续租（renew）与租约看门狗。

续租是条件更新：仅当 id、status='running'、lease_owner、lease_revision
全部匹配且原租约尚未到期时才延长 lease_until（DD 9.2）。0 行 → LostLease：
调用方必须中止 handler 且不得提交结果。
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from sqlalchemy import Engine, text

from ..logging_setup import mlog
from .rows import JobRow

log = logging.getLogger("mvp_worker.renew")


class LostLease(RuntimeError):
    """当前代次不再持有有效租约（被回收/代次不符/已过期）。禁止提交结果。"""


_RENEW = text(
    """
UPDATE async_jobs
SET lease_until = CURRENT_TIMESTAMP + make_interval(secs => :lease_seconds),
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND status = 'running'
  AND lease_owner = :worker_id
  AND lease_revision = :lease_revision
  AND lease_until >= CURRENT_TIMESTAMP
"""
)


def renew(
    engine: Engine,
    job_id: str,
    lease_owner: str,
    lease_revision: int,
    *,
    lease_seconds: int,
) -> bool:
    """成功延长租约返回 True；代次/状态/时效任一不符抛 LostLease。"""
    with engine.begin() as conn:
        res = conn.execute(
            _RENEW,
            {
                "id": job_id,
                "worker_id": lease_owner,
                "lease_revision": int(lease_revision),
                "lease_seconds": int(lease_seconds),
            },
        )
    if res.rowcount == 0:
        raise LostLease(
            f"job {job_id} lease lost (owner={lease_owner}, revision={lease_revision})"
        )
    return True


class LeaseRenewer:
    """每领取任务一个后台续租看门狗：每 renew_interval 续租一次；
    LostLease → 置 abort_event（协作式），handler 线程应在提交前检查并停止。"""

    def __init__(
        self,
        engine: Engine,
        claim: JobRow,
        *,
        lease_seconds: int,
        renew_interval_seconds: float,
        abort_event: threading.Event,
    ) -> None:
        self._engine = engine
        self._claim = claim
        self._lease_seconds = lease_seconds
        self._interval = float(renew_interval_seconds)
        self._abort = abort_event
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "LeaseRenewer":
        self._thread = threading.Thread(
            target=self._run,
            name=f"lease-renew-{self._claim.id[:8]}",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        claim = self._claim
        while not self._stop.wait(self._interval):
            try:
                renew(
                    self._engine,
                    claim.id,
                    claim.lease_owner,
                    claim.lease_revision,
                    lease_seconds=self._lease_seconds,
                )
            except LostLease:
                mlog(
                    log,
                    logging.WARNING,
                    "lease.lost",
                    workerId=claim.lease_owner,
                    **claim.log_fields(),
                )
                self._abort.set()  # 协作式中止：完成事务前 handler 必须停
                return
            except Exception:  # DB 抖动等：下一周期再试，租约自然过期由回收器接管
                mlog(
                    log,
                    logging.ERROR,
                    "lease.renew_error",
                    workerId=claim.lease_owner,
                    **claim.log_fields(),
                    errorType="renew_exception",
                )
        # stop 被置位 → 正常退出
