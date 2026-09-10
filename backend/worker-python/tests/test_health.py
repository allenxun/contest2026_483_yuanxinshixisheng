"""健康端点（测试端口 18081，避开宿主/默认端口）。"""
from __future__ import annotations

import dataclasses
import json
import urllib.error
import urllib.request

from sqlalchemy import Engine, text

from conftest import enqueue
from mvp_worker.config import WorkerConfig
from mvp_worker.health import start_health_server

TEST_PORT = 18081


def _get(path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}{path}", timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_healthz_and_readyz(engine: Engine, test_dsn: str) -> None:
    cfg = dataclasses.replace(
        WorkerConfig(runtime_dsn=test_dsn),
        health_host="127.0.0.1",
        health_port=TEST_PORT,
    )
    server = start_health_server(cfg, engine)
    try:
        status, body = _get("/healthz")
        assert status == 200
        assert body["status"] == "UP"
        assert body["workerId"] == cfg.worker_id

        # 无 queued → age null
        status, body = _get("/readyz")
        assert status == 200
        assert body == {"status": "UP", "db": True, "oldestQueuedJobAgeSeconds": None}

        # 最老待办 10 秒 → 年龄 ≈10
        jid, _ = enqueue(engine)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE async_jobs SET available_at = CURRENT_TIMESTAMP "
                     "- interval '10 seconds' WHERE id = :id"),
                {"id": jid},
            )
        status, body = _get("/readyz")
        assert status == 200
        assert body["db"] is True
        assert 9 <= body["oldestQueuedJobAgeSeconds"] <= 13
    finally:
        server.shutdown()
        server.server_close()


def test_readyz_db_down_returns_503(engine: Engine, test_dsn: str) -> None:
    """DB 不可达 → 503 DOWN（readyz 反映真实依赖）。"""
    from mvp_worker.db import create_db_engine

    bad = create_db_engine(
        "postgresql://postgres:x@127.0.0.1:1/none", pool_size=1, max_overflow=0
    )
    cfg = dataclasses.replace(
        WorkerConfig(runtime_dsn=test_dsn),
        health_host="127.0.0.1",
        health_port=TEST_PORT,
    )
    server = start_health_server(cfg, bad)
    try:
        try:
            _get("/readyz")
            raise AssertionError("expected HTTPError 503")
        except urllib.error.HTTPError as err:
            assert err.code == 503
            body = json.loads(err.read().decode("utf-8"))
            assert body["status"] == "DOWN"
    finally:
        server.shutdown()
        server.server_close()
        bad.dispose()
