"""运行循环：recover → claim → 线程池分发（每任务一个续租看门狗）→ 代次受控完成。

- 至少一次执行：handler 可能在崩溃/回收后重复运行；正式落地由完成事务的
  代次守卫 + 业务输入版本复核阻断（不宣称 exactly-once）。
- 优雅停机（SIGTERM/SIGINT）：停止领取新任务；等待在途 handler 完成其
  （短）完成事务；未及完成的由租约过期回收接管（ARCH 11.2）。
- 未知 job_type / 未注册 handler / payload 契约不符 → fail_unsupported，
  直接 failed 不循环（B/C/D 业务类型在 A 包即走此扩展点路径）。
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

from sqlalchemy import Engine

from ..config import WorkerConfig
from ..db import create_db_engine
from ..handlers import (
    HandlerContext,
    JobFailed,
    UnsupportedPayload,
    get_handler,
)
from ..logging_setup import mlog
from .claim import claim_batch
from .complete import (
    BusinessTx,
    StaleGeneration,
    complete_deferred,
    complete_failure,
    complete_success,
    fail_unsupported,
)
from .expire import recover_expired, release_claim
from .renew import LeaseRenewer
from .rows import JobRow

log = logging.getLogger("mvp_worker.loop")


class WorkerRuntime:
    def __init__(self, config: WorkerConfig, engine: Optional[Engine] = None) -> None:
        self.cfg = config
        self.engine = engine or create_db_engine(
            config.runtime_dsn,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
        )
        self.stop_event = threading.Event()
        # 进程内周期扫描器（C8）：延迟构造，只有 run_forever 需要；--once/--recover
        # 不触发，保持既有单周期/回收语义不变。
        self._scanner = None

    def dispose(self) -> None:
        self.engine.dispose()

    def _scanner_or_build(self):
        """构造/复用进程内周期扫描器（B 的 incident.scan + D 的 media.cleanup.discover）。"""
        if self._scanner is None:
            from ..scanners.scheduler import build_worker_scanner

            self._scanner = build_worker_scanner(self.cfg, self.engine)
        return self._scanner

    # ---------------- dispatch ----------------

    def process_job(self, claim: JobRow) -> None:
        """处理一个已领取（running，新代次）任务。所有 DB 写都是字段级条件更新。"""
        worker_id = self.cfg.worker_id
        fields = claim.log_fields()
        mlog(log, logging.INFO, "job.claimed", workerId=worker_id, **fields)

        handler = get_handler(claim.job_type)
        if handler is None:
            # A 包扩展点：B/C/D 注册业务 handler 前，此类任务在此隔离（不重试循环）
            mlog(
                log,
                logging.WARNING,
                "job.unsupported_type",
                workerId=worker_id,
                **fields,
                note="no registered handler: extension point for B/C/D",
            )
            self._write_unsupported(claim, message=(
                f"no registered handler for job_type={claim.job_type} "
                "(extension point for B/C/D)"
            ))
            return

        try:
            handler.validate(claim.payload)
        except UnsupportedPayload as exc:
            mlog(log, logging.WARNING, "job.payload_unsupported",
                 workerId=worker_id, **fields, reason=str(exc)[:300])
            self._write_unsupported(claim, message=str(exc)[:500])
            return

        abort_event = threading.Event()
        ctx = HandlerContext(
            engine=self.engine, config=self.cfg, job=claim, abort_event=abort_event
        )
        renewer = LeaseRenewer(
            self.engine,
            claim,
            lease_seconds=self.cfg.lease_seconds,
            renew_interval_seconds=self.cfg.renew_interval_seconds,
            abort_event=abort_event,
        ).start()
        try:
            result = handler.handle(ctx, claim)
        except JobFailed as exc:
            self._finish_failure(
                claim, exc.code, exc.message, exc.retryable, business_tx=exc.business_tx
            )
            return
        except Exception as exc:  # 未预期异常 → 按临时错误退避重试
            mlog(log, logging.ERROR, "job.handler_exception",
                 workerId=worker_id, **fields, errorClass=type(exc).__name__)
            self._finish_failure(
                claim, "HANDLER_ERROR", f"unhandled {type(exc).__name__}", retryable=True
            )
            return
        finally:
            renewer.stop()

        if abort_event.is_set():
            # 租约已丢：结果不提交、不作废（回收器已/将重新入队，新代次接管）
            mlog(log, logging.WARNING, "job.result_abandoned_lease_lost",
                 workerId=worker_id, **fields)
            return
        defer_seconds = result.defer_seconds if result is not None else None
        deferred = defer_seconds is not None
        try:
            if defer_seconds is not None:
                # 合法等待态：同 job 重排并退还本次 attempt（不产生后继任务）
                complete_deferred(
                    self.engine,
                    claim,
                    defer_seconds=float(defer_seconds),
                    business_tx=result.business_tx if result is not None else None,
                )
            else:
                complete_success(
                    self.engine,
                    claim,
                    handler_result_tx=result.business_tx if result is not None else None,
                )
        except StaleGeneration:
            mlog(log, logging.WARNING, "job.complete_stale_generation",
                 workerId=worker_id, **fields,
                 note="rolled back; recovery owns the job now")
            return
        mlog(log, logging.INFO, "job.deferred" if deferred else "job.succeeded",
             workerId=worker_id, **fields)

    def _write_unsupported(self, claim: JobRow, *, message: str) -> None:
        try:
            fail_unsupported(self.engine, claim, message=message)
        except StaleGeneration:
            mlog(log, logging.WARNING, "job.unsupported_stale_generation",
                 workerId=self.cfg.worker_id, **claim.log_fields())

    def _finish_failure(
        self,
        claim: JobRow,
        code: str,
        message: str,
        retryable: bool,
        *,
        business_tx: Optional[BusinessTx] = None,
    ) -> None:
        try:
            complete_failure(
                self.engine,
                claim,
                code=code,
                message=message,
                retryable=retryable,
                backoff_base_seconds=self.cfg.backoff_base_seconds,
                backoff_cap_seconds=self.cfg.backoff_cap_seconds,
                business_tx=business_tx,
            )
        except StaleGeneration:
            # 失败写回也可能遇 stale：回收器已重新入队，丢弃本写回即可
            mlog(log, logging.WARNING, "job.failure_write_stale_generation",
                 workerId=self.cfg.worker_id, **claim.log_fields())
            return
        mlog(log, logging.INFO, "job.failure_recorded",
             workerId=self.cfg.worker_id, **claim.log_fields(), code=code)

    # ---------------- cycles ----------------

    def run_cycle(self) -> int:
        """回收过期 → 领取一批 → 线程池并发处理并等待全部落定。返回处理数。"""
        recovered = recover_expired(self.engine)
        if recovered:
            mlog(log, logging.INFO, "jobs.recovered_expired",
                 workerId=self.cfg.worker_id, count=recovered)
        claims = claim_batch(
            self.engine,
            worker_id=self.cfg.worker_id,
            lease_seconds=self.cfg.lease_seconds,
            batch_size=self.cfg.claim_batch,
        )
        if not claims:
            return 0
        pool = ThreadPoolExecutor(
            max_workers=self.cfg.claim_batch, thread_name_prefix="mvp-job"
        )
        futures: list[Future] = []
        try:
            for claim in claims:
                futures.append(pool.submit(self.process_job, claim))
        finally:
            pool.shutdown(wait=True)
        # 线程内已捕获全部业务/写回异常；这里只暴露循环自身的意外
        for fut in futures:
            exc = fut.exception()
            if exc is not None:
                mlog(log, logging.ERROR, "job.loop_exception",
                     workerId=self.cfg.worker_id, errorClass=type(exc).__name__)
        return len(claims)

    def run_forever(self) -> None:
        mlog(log, logging.INFO, "worker.start",
             workerId=self.cfg.worker_id, environment=self.cfg.environment)
        # C8：两个有界周期扫描任务挂在既有循环里，与 run_cycle 同线程：
        # - 挂载点 = 每轮 run_cycle 之后（批处理间隙），到期才跑、上一轮未完成不叠加；
        # - 扫描回调只做有界 DB 读写/入队，异常自隔离，绝不终止 Worker；
        # - 等待窗口收敛到最近到期时间，stop_event 仍可立即唤醒（停机延迟不变大）。
        scanner = self._scanner_or_build()
        while not self.stop_event.is_set():
            try:
                processed = self.run_cycle()
            except Exception as exc:  # DB 抖动等：等一个 poll 周期重试（租约/回收兜底）
                mlog(log, logging.ERROR, "worker.cycle_error",
                     workerId=self.cfg.worker_id, errorClass=type(exc).__name__)
                processed = 0
            scanner.run_due()
            if self.stop_event.is_set():
                break
            if processed == 0:
                # 空闲：等待 min(poll, 最近扫描到期)，两者都能被 stop_event 立即唤醒
                self.stop_event.wait(
                    scanner.next_wait_seconds(self.cfg.poll_interval_seconds)
                )
        # 优雅停机：run_cycle 等待了全部在途 future；此处无遗留领取
        mlog(log, logging.INFO, "worker.stopped", workerId=self.cfg.worker_id)
