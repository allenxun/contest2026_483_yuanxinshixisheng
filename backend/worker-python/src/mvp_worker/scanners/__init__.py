"""B 包扫描器入口：``python -m mvp_worker.scanners --once``。

进程内周期触发由总协调在集成时接入（C8）；本模块只提供可重入
:func:`run_once` 与供验证的 CLI，不新增常驻进程/定时服务。
"""
from __future__ import annotations

from .incident_scanner import ScanReport, run_once

__all__ = ["ScanReport", "run_once"]


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
    parser.add_argument("--loop", action="store_true", help="周期运行（本轮不接入部署）")
    parser.add_argument("--interval", type=int, default=None, help="周期秒数（覆盖配置默认）")
    args = parser.parse_args(argv)

    setup_logging()
    cfg = WorkerConfig()
    settings = load_settings()
    engine = create_db_engine(cfg.runtime_dsn, pool_size=2, max_overflow=cfg.max_overflow)
    try:
        if args.loop:
            interval = args.interval or settings.scan_interval_seconds
            while True:
                report = run_once(engine, settings)
                print(json.dumps(report.to_dict(), ensure_ascii=False), flush=True)
                time.sleep(interval)
        report = run_once(engine, settings)
        print(json.dumps(report.to_dict(), ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        engine.dispose()
