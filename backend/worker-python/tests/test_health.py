"""健康端点（测试绑 0 端口 → 读回 OS 分配端口，避开宿主/外部进程端口冲突）。

不使用固定端口：``health_port=0`` 让内核分配一个测试独占的临时端口，随后从
``start_health_server`` 返回的 server 对象读回实际端口（无 probe-then-release 竞态）。
"""
from __future__ import annotations

import dataclasses
import json
import urllib.error
import urllib.request
from typing import Any

from sqlalchemy import Engine, text

from conftest import enqueue
from mvp_worker.config import WorkerConfig
from mvp_worker.health import start_health_server


def _bound_port(server: Any) -> int:
    """读回 server 实际绑定端口（``health_port=0`` → OS 分配）。

    ``health.py`` 在构造 ``_HealthServer((host, port), _Handler)`` 时立即 bind
    （``ThreadingHTTPServer.__init__`` → ``server_bind``），故 ``server_address``
    已就绪；回退到 ``socket.getsockname()``。启动/探测/清理全程使用该端口。
    """
    addr = getattr(server, "server_address", None)
    if addr is not None:
        return int(addr[1])
    return int(server.socket.getsockname()[1])


def _get(port: int, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_healthz_and_readyz(engine: Engine, test_dsn: str) -> None:
    cfg = dataclasses.replace(
        WorkerConfig(runtime_dsn=test_dsn),
        health_host="127.0.0.1",
        health_port=0,  # 内核分配测试独占端口
    )
    server = start_health_server(cfg, engine)
    try:
        port = _bound_port(server)
        status, body = _get(port, "/healthz")
        assert status == 200
        assert body["status"] == "UP"
        assert body["workerId"] == cfg.worker_id

        # 无 queued → age null
        status, body = _get(port, "/readyz")
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
        status, body = _get(port, "/readyz")
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
        health_port=0,  # 内核分配测试独占端口
    )
    server = start_health_server(cfg, bad)
    try:
        port = _bound_port(server)
        try:
            _get(port, "/readyz")
            raise AssertionError("expected HTTPError 503")
        except urllib.error.HTTPError as err:
            assert err.code == 503
            body = json.loads(err.read().decode("utf-8"))
            assert body["status"] == "DOWN"
    finally:
        server.shutdown()
        server.server_close()
        bad.dispose()
