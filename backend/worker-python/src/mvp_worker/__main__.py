"""命令行入口：``python -m mvp_worker``。

- 默认（无参数）：运行循环（recover → claim → dispatch → complete）+ 健康端点，
  SIGTERM/SIGINT 优雅停机（停止领取，等待在途完成事务；未完成者由租约回收接管）。
- ``--check``：连接 PostgreSQL 打印服务端版本后退出（骨架自检行为，保持不变）。
- ``--once``：单周期 claim/dispatch/complete 后退出 0（跨语言 E2E 测试用；
  不启动健康端点，避免测试端口冲突）。
- ``--recover``：执行一次过期回收并打印条数。
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys

import psycopg

from .config import WorkerConfig
from .logging_setup import mlog, setup_logging

log = logging.getLogger("mvp_worker.main")


def _check(cfg: WorkerConfig) -> int:
    with psycopg.connect(cfg.check_dsn) as cur:  # type: ignore[call-arg]
        row = cur.execute("SHOW server_version").fetchone()
    print(f"PostgreSQL server_version: {row[0] if row else 'unknown'}")
    return 0


def _run_recover(cfg: WorkerConfig) -> int:
    from .runtime.expire import recover_expired

    from .db import create_db_engine

    engine = create_db_engine(
        cfg.runtime_dsn, pool_size=1, max_overflow=cfg.max_overflow
    )
    try:
        count = recover_expired(engine)
    finally:
        engine.dispose()
    print(f"recovered_expired_jobs: {count}")
    return 0


def _run_once(cfg: WorkerConfig) -> int:
    from .runtime.loop import WorkerRuntime

    rt = WorkerRuntime(cfg)
    try:
        processed = rt.run_cycle()
    finally:
        rt.dispose()
    print(f"once_cycle_processed_jobs: {processed}")
    return 0


def _run_forever(cfg: WorkerConfig) -> int:
    from .db import create_db_engine
    from .health import start_health_server
    from .runtime.loop import WorkerRuntime

    engine = create_db_engine(
        cfg.runtime_dsn, pool_size=cfg.pool_size, max_overflow=cfg.max_overflow
    )
    rt = WorkerRuntime(cfg, engine=engine)
    server = start_health_server(cfg, engine)

    def _stop(signum: int, _frame: object) -> None:
        mlog(log, logging.INFO, "worker.signal_stop",
             workerId=cfg.worker_id, signal=signum)
        rt.stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        rt.run_forever()
    finally:
        server.shutdown()
        server.server_close()
        engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mvp_worker")
    parser.add_argument(
        "--check",
        action="store_true",
        help="连接 PostgreSQL、打印服务端版本并退出（不启动运行循环）",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="执行单个回收+领取+处理+完成周期后退出（E2E 测试用）",
    )
    parser.add_argument(
        "--recover",
        action="store_true",
        help="执行一次租约过期回收并打印条数",
    )
    args = parser.parse_args(argv)

    cfg = WorkerConfig()
    if args.check:
        return _check(cfg)

    setup_logging()
    if args.recover:
        return _run_recover(cfg)
    if args.once:
        return _run_once(cfg)
    return _run_forever(cfg)


if __name__ == "__main__":
    sys.exit(main())
