"""B 包扫描器入口：``python -m mvp_worker.scanners --once``。

进程内周期触发**已接入既有 Worker**（按 C8 裁定，不加常驻进程/cron/部署调度）：
``runtime/loop.py`` 的 ``run_forever()`` 在每轮 ``run_cycle()`` 之后调用
``scanners.scheduler.PeriodicScheduler.run_due()``，空闲等待窗口取
``min(poll_interval, next_wait_seconds)``，由 :mod:`.scheduler` 装配 B 的 incident
扫描与 D 的 ``media.cleanup`` 候选发现两个有界周期任务。

本模块提供可重入 :func:`run_once`，以及供验证/排障的 CLI：``--once`` 单轮有界扫描
（退出码语义不变）、``--loop`` 为**进程内验证用**循环（跨轮持 keyset 游标），
生产周期触发不依赖本 CLI。
"""
from __future__ import annotations

from .incident_scanner import ScanCursors, ScanReport, run_once

__all__ = ["ScanCursors", "ScanReport", "run_once"]


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import time

    from ..config import WorkerConfig
    from ..db import create_db_engine
    from ..logging_setup import setup_logging
    from ..notifications.config import load_settings

    parser = argparse.ArgumentParser(prog="mvp_worker.scanners")
    parser.add_argument("--once", action="store_true", help="执行单轮扫描后退出（验证用）")
    parser.add_argument("--loop", action="store_true", help="周期运行（进程内验证用；生产周期触发已接入既有 Worker）")
    parser.add_argument("--interval", type=int, default=None, help="周期秒数（覆盖配置默认）")
    parser.add_argument(
        "--limit", type=int, default=None, help="单轮每个候选阶段的批量上限（默认取配置）"
    )
    args = parser.parse_args(argv)

    setup_logging()
    cfg = WorkerConfig()
    settings = load_settings()
    limit = args.limit if args.limit is not None else cfg.incident_scan_batch
    engine = create_db_engine(cfg.runtime_dsn, pool_size=2, max_overflow=cfg.max_overflow)
    try:
        if args.loop:
            # 进程内循环验证用：持有 keyset 游标，逐轮有界推进。
            # 生产周期触发见 runtime/loop.py + scanners/scheduler.py（C8）。
            interval = args.interval or cfg.incident_scan_interval_seconds
            cursors = ScanCursors()
            while True:
                report = run_once(engine, settings, limit=limit, cursors=cursors)
                print(json.dumps(report.to_dict(), ensure_ascii=False), flush=True)
                time.sleep(interval)
        # --once：单轮有界扫描（退出码语义不变）。
        report = run_once(engine, settings, limit=limit)
        print(json.dumps(report.to_dict(), ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        engine.dispose()
