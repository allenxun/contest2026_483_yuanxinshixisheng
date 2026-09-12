"""进程内周期调度器：把可重入扫描任务挂到既有 Worker 循环（C8 裁定）。

约束与实现选择：
- **不新增服务/进程/队列/线程**：本模块只是被 ``runtime/loop.py`` 的 ``run_forever``
  在同一线程里调用；扫描任务是既有 :func:`incident_scanner.run_once` 与 D 的
  :func:`media_cleanup.discover_and_enqueue_orphans`。
- **到期才触发**：每个任务维护 ``due_at``（``time.monotonic`` 时钟）；``run_due``
  只运行 ``due_at <= now`` 的任务，运行后顺延 ``interval``。
- **上一轮未完成不叠加并发**：每个任务一把非阻塞 ``threading.Lock``；拿不到锁
  即跳过本轮并顺延，不排队、不叠加。
- **多实例重叠安全**：不做任何新分布式锁；并发正确性依赖既有机制
  （离线扫描的 ``SELECT ... FOR UPDATE`` + ``status_revision``、通知/任务复合唯一键
  ``uq_notification_dedup``/``uq_job_dedup``、D 的 dedup_key）。
- **有界**：任务回调由调用方传入显式 ``limit``；隔离异常（单任务失败不改 Worker）。
- **网络不在锁内**：扫描回调只做 DB 读写与入队，不发任何网络/存储请求（存储删除
  在 ``media.cleanup`` handler 里、事务锁外执行，与本调度无关）。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy import Engine

from ..config import WorkerConfig
from ..logging_setup import mlog

log = logging.getLogger("mvp_worker.scanners.scheduler")

#: 回调返回的可观测字典；键名一律为聚合计数，**绝不**含 payload/token/身份。
ScanCallback = Callable[[], dict[str, Any]]


@dataclass
class TaskOutcome:
    """单次任务运行结果（仅聚合量，用于日志与测试断言）。"""

    name: str
    ran: bool
    error: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)


class PeriodicTask:
    """一个周期任务：间隔 + 到期时间 + 非阻塞重入守卫。"""

    def __init__(self, name: str, interval_seconds: int, callback: ScanCallback) -> None:
        self.name = name
        self.interval_seconds = max(1, int(interval_seconds))
        self._callback = callback
        self._guard = threading.Lock()
        # 首个周期立即到期：进程启动即补扫一次，之后按 interval 顺延。
        #
        # 调度语义为 **fixed-rate / best-effort**（有意如此，非缺陷）：``due_at`` 以
        # 本次尝试**开始前**的 ``now`` 顺延（见 :meth:`attempt` 的 finally），故当回调
        # 耗时超过 ``interval`` 时下一轮会立即到期——不补偿漂移、也不跳过周期。
        # 叠加并发由下面的非阻塞守卫排除；若将来需要"固定延迟"语义（回调结束后再等
        # 一个 interval），应在 finally 中改用回调结束时的 monotonic 时间。
        self.due_at = 0.0

    def attempt(self, now: float) -> Optional[TaskOutcome]:
        """到点后的单次尝试；守卫被占则跳过并顺延（返回 None）。"""
        if not self._guard.acquire(blocking=False):
            self.due_at = now + self.interval_seconds
            return None
        try:
            detail = self._callback() or {}
            return TaskOutcome(name=self.name, ran=True, detail=detail)
        except Exception as exc:  # 单任务失败隔离：绝不终止 Worker 循环
            return TaskOutcome(name=self.name, ran=True, error=type(exc).__name__)
        finally:
            self.due_at = now + self.interval_seconds
            self._guard.release()


class PeriodicScheduler:
    """有界周期任务的到期检查器（单线程调用；时钟可注入便于测试）。"""

    def __init__(
        self,
        tasks: list[PeriodicTask],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._tasks = list(tasks)
        self._clock = clock

    @property
    def tasks(self) -> list[PeriodicTask]:
        return list(self._tasks)

    def next_wait_seconds(self, max_wait: float) -> float:
        """返回下一次需要醒来的等待秒数：``min(最近到期, max_wait)``。

        用于把 ``stop_event.wait`` 的窗口收敛到"最近一个扫描到期时间"，既保证
        扫描按时触发，又保证 ``stop_event`` 能及时唤醒（停机延迟不显著变大）。
        """
        if not self._tasks:
            return max_wait
        now = self._clock()
        soonest = min(task.due_at for task in self._tasks)
        delay = soonest - now
        if delay <= 0:
            return 0.0
        return float(min(max_wait, delay))

    def run_due(self) -> list[TaskOutcome]:
        """运行所有已到期任务；每个任务独立隔离异常与日志。"""
        now = self._clock()
        outcomes: list[TaskOutcome] = []
        for task in self._tasks:
            if task.due_at > now:
                continue
            outcome = task.attempt(now)
            if outcome is None:
                # 守卫被占（异常情况下另一线程仍在跑）：顺延即可，不叠加。
                mlog(
                    log, logging.WARNING, "scanner.task_skipped_overlap",
                    task=task.name,
                )
                continue
            if outcome.error:
                mlog(
                    log, logging.ERROR, "scanner.task_failed",
                    task=outcome.name, errorClass=outcome.error,
                )
            else:
                mlog(
                    log, logging.INFO, "scanner.task_ran",
                    task=outcome.name, **outcome.detail,
                )
            outcomes.append(outcome)
        return outcomes


def build_worker_scanner(cfg: WorkerConfig, engine: Engine) -> PeriodicScheduler:
    """构造既有 Worker 进程内使用的两个有界周期扫描任务。

    - ``incident.scan``：B 的离线/异常扫描，``cfg.incident_scan_interval_seconds`` /
      ``cfg.incident_scan_batch``，跨轮持有 :class:`ScanCursors` keyset 游标；
    - ``media.cleanup.discover``：D 的孤儿候选发现，``cfg.media_cleanup_scan_interval_seconds``
      / ``cfg.media_cleanup_scan_batch``（入队仍是既有 dedup 幂等语义）。

    延迟 import 扫描实现，避免本模块在纯单元测试里拉起 DB/契约依赖。
    """
    from ..handlers.media_cleanup import discover_and_enqueue_orphans
    from ..notifications.config import load_settings
    from .incident_scanner import ScanCursors, run_once

    settings = load_settings()
    cursors = ScanCursors()

    def _incident() -> dict[str, Any]:
        report = run_once(
            engine, settings, limit=cfg.incident_scan_batch, cursors=cursors
        )
        return report.to_dict()

    def _media_cleanup() -> dict[str, Any]:
        enqueued = discover_and_enqueue_orphans(
            engine, limit=cfg.media_cleanup_scan_batch
        )
        return {"enqueued": enqueued}

    return PeriodicScheduler(
        [
            PeriodicTask(
                "incident.scan", cfg.incident_scan_interval_seconds, _incident
            ),
            PeriodicTask(
                "media.cleanup.discover",
                cfg.media_cleanup_scan_interval_seconds,
                _media_cleanup,
            ),
        ]
    )
