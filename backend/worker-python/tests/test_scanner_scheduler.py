"""进程内周期扫描调度（C8）测试：到期触发、批量上限/keyset、重入安全、
stop_event 及时停机、同轮有界，以及 C7 离线扫描不写 ``last_seen_at`` 红线。

真实 PG @55435/``mvp_b_dev``（经 conftest 临时库）。D 的 ``media.cleanup`` 候选
发现有界性在本文件断言；D 既有 ``tests/test_media_cleanup.py`` 仍作为语义未变对照。
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Optional

from sqlalchemy import Engine, text

from b_support import b_clean_tables  # noqa: F401  autouse B 自清
from d_support import seed_media
from test_notification_support import (
    fetch_gimbal,
    make_past,
    seed_account,
    seed_destination,
    seed_gimbal,
)

from mvp_worker.config import WorkerConfig
from mvp_worker.handlers.media_cleanup import discover_and_enqueue_orphans
from mvp_worker.media.storage import FilesystemStorageDouble
from mvp_worker.notifications.config import NotificationSettings
from mvp_worker.runtime.loop import WorkerRuntime
from mvp_worker.scanners import ScanCursors, run_once
from mvp_worker.scanners.scheduler import (
    PeriodicScheduler,
    PeriodicTask,
    build_worker_scanner,
)


def _settings(threshold: int = 60) -> NotificationSettings:
    return NotificationSettings(offline_threshold_seconds=threshold)


# ---------------- ①② 到期才触发 / 未到期不触发 ----------------


def test_periodic_task_triggers_only_when_due() -> None:
    calls: list[int] = []

    def callback() -> dict[str, Any]:
        calls.append(1)
        return {"n": 1}

    clock = {"now": 50.0}
    task = PeriodicTask("t", 30, callback)
    task.due_at = 100.0
    sched = PeriodicScheduler([task], clock=lambda: clock["now"])

    assert sched.run_due() == []  # 未到期：不触发
    assert calls == []
    assert sched.next_wait_seconds(2) == 2.0  # min(poll=2, 距到期 50)

    clock["now"] = 99.999
    assert sched.run_due() == []
    assert calls == []

    clock["now"] = 100.0
    outcomes = sched.run_due()  # 到期：触发一次
    assert [o.name for o in outcomes] == ["t"]
    assert calls == [1]
    assert task.due_at == 130.0  # 运行后顺延
    assert sched.run_due() == []  # 刚跑过，未到期


def test_next_wait_seconds_uses_sooner_of_poll_and_due() -> None:
    clock = {"now": 10.0}
    task = PeriodicTask("t", 30, lambda: {})
    task.due_at = 10.5
    sched = PeriodicScheduler([task], clock=lambda: clock["now"])
    assert abs(sched.next_wait_seconds(2) - 0.5) < 1e-9
    task.due_at = 100.0
    assert sched.next_wait_seconds(2) == 2.0


# ---------------- ③ 重入 / 重叠安全 ----------------


def test_periodic_task_does_not_overlap_when_previous_still_running() -> None:
    started = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def callback() -> dict[str, Any]:
        calls["n"] += 1
        started.set()
        assert release.wait(timeout=5), "callback never released"
        return {"n": calls["n"]}

    clock = lambda: 100.0  # noqa: E731
    task = PeriodicTask("t", 30, callback)
    task.due_at = 100.0
    sched = PeriodicScheduler([task], clock=clock)

    runner = threading.Thread(target=sched.run_due, daemon=True)
    runner.start()
    assert started.wait(timeout=5)

    # 上一轮仍在进行（守卫被占）：同一到期点再次 run_due 不得叠加并发。
    assert sched.run_due() == []
    assert calls["n"] == 1

    release.set()
    runner.join(timeout=5)
    assert calls["n"] == 1
    assert task.due_at == 130.0


# ---------------- ①/② 两个任务独立间隔与批量（真实 PG 装配） ----------------


def test_build_worker_scanner_wires_two_independent_tasks(
    engine: Engine, test_dsn: str
) -> None:
    cfg = WorkerConfig(
        runtime_dsn=test_dsn,
        incident_scan_interval_seconds=11,
        incident_scan_batch=7,
        media_cleanup_scan_interval_seconds=22,
        media_cleanup_scan_batch=3,
    )
    sched = build_worker_scanner(cfg, engine)
    by_name = {task.name: task for task in sched.tasks}
    assert set(by_name) == {"incident.scan", "media.cleanup.discover"}
    assert by_name["incident.scan"].interval_seconds == 11
    assert by_name["media.cleanup.discover"].interval_seconds == 22

    # 首次到期即触发两个任务（空库上各自有界 no-op，不抛异常）。
    outcomes = sched.run_due()
    assert {o.name for o in outcomes} == {"incident.scan", "media.cleanup.discover"}
    assert all(o.error is None for o in outcomes)
    assert all(isinstance(o.detail, dict) for o in outcomes)


# ---------------- ④ stop_event 及时停止 ----------------


def test_run_forever_stops_promptly(engine: Engine, test_dsn: str) -> None:
    cfg = WorkerConfig(
        runtime_dsn=test_dsn,
        poll_interval_seconds=1,
        incident_scan_interval_seconds=30,
        media_cleanup_scan_interval_seconds=30,
    )
    rt = WorkerRuntime(cfg, engine=engine)
    runner = threading.Thread(target=rt.run_forever, daemon=True)
    runner.start()
    time.sleep(0.3)  # 让它至少跑一轮（run_cycle + run_due），并进入等待窗口
    started = time.monotonic()
    rt.stop_event.set()
    runner.join(timeout=5)
    assert not runner.is_alive(), "run_forever 未在 stop_event 后及时退出"
    # 等待窗口被 stop_event 立即打断（远小于扫描间隔，也小于 wait 上限）
    assert time.monotonic() - started < 3


# ---------------- ② 批量上限 + keyset 推进（incident.scan） ----------------


def _offline_count(engine: Engine, gimbal_ids: list[uuid.UUID]) -> int:
    total = 0
    with engine.connect() as conn:
        for gid in gimbal_ids:
            total += int(
                conn.execute(
                    text(
                        "SELECT count(*) FROM gimbals WHERE id = :id"
                        " AND connection_status = 'offline'"
                    ),
                    {"id": gid},
                ).scalar_one()
            )
    return total


def test_incident_scan_batch_limit_and_keyset_progress(engine: Engine) -> None:
    account = seed_account(engine)
    seed_destination(engine, account_id=account, revision=1, session_ref="sess-1")
    gimbals = [
        seed_gimbal(
            engine, account_id=account, binding_revision=1, status="online",
            last_seen_at=make_past(3600), episodes={},
        )
        for _ in range(5)
    ]
    cursors = ScanCursors()

    first = run_once(engine, _settings(), limit=2, cursors=cursors)
    assert first.scan_limit == 2
    assert first.offline_candidates == 2  # 单轮只取一页
    assert _offline_count(engine, gimbals) == 2
    assert cursors.offline_after_id is not None  # 取满一页 → 游标推进

    second = run_once(engine, _settings(), limit=2, cursors=cursors)
    assert second.offline_candidates == 2
    assert _offline_count(engine, gimbals) == 4  # 下一轮继续，不重扫前缀

    third = run_once(engine, _settings(), limit=2, cursors=cursors)
    assert _offline_count(engine, gimbals) == 5  # 到尾：剩余不足一页
    assert cursors.offline_after_id is None  # 到尾部 → 游标归零，下一轮从头

    # 未分页（limit=None）保持既有整轮语义，ScanReport 形状含新增 scan_limit 字段。
    legacy = run_once(engine, _settings())
    assert legacy.scan_limit is None
    assert set(legacy.to_dict()) >= {
        "offline_candidates", "marked_offline", "episodes_opened", "notifications_created",
        "jobs_enqueued", "failures", "failure_codes",
    }


# ---------------- ⑤ C7：离线扫描绝不写 last_seen_at ----------------


def _read_last_seen(engine: Engine, gimbal_id: uuid.UUID) -> Optional[Any]:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT last_seen_at FROM gimbals WHERE id = :id"), {"id": gimbal_id}
        ).scalar_one()


def test_offline_scan_never_writes_last_seen_at(engine: Engine) -> None:
    account = seed_account(engine)
    seed_destination(engine, account_id=account, revision=1, session_ref="sess-1")
    gimbal = seed_gimbal(
        engine, account_id=account, binding_revision=1, status="online",
        last_seen_at=make_past(3600), episodes={},
    )

    before = _read_last_seen(engine, gimbal)
    run_once(engine, _settings())
    after = _read_last_seen(engine, gimbal)

    assert fetch_gimbal(engine, gimbal)["connection_status"] == "offline"  # 确实判离线
    assert before == after  # C7 红线：last_seen_at 一字未改（仅心跳路径可写）


# ---------------- ⑥ D：media.cleanup 候选发现有界、语义未变 ----------------


def test_media_cleanup_discovery_is_bounded(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    for _ in range(5):
        seed_media(engine, storage, state="available")  # 无归属、可清理孤儿

    enqueued = discover_and_enqueue_orphans(engine, limit=2)
    assert enqueued == 2  # 单轮只发现一页，不整表处理

    with engine.connect() as conn:
        total = int(
            conn.execute(
                text(
                    "SELECT count(*) FROM async_jobs"
                    " WHERE dedup_key LIKE 'media:%:cleanup:1'"
                )
            ).scalar_one()
        )
    assert total == 2  # 只有一页候选入队；余下候选留待后续轮次（有界）

    # 再发现：同一批已入队候选 dedup 命中 → 0 新任务（幂等语义未变）。
    assert discover_and_enqueue_orphans(engine, limit=2) == 0
