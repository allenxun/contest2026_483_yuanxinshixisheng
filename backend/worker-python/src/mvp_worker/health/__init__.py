"""Worker 健康端点（stdlib http.server，仅随运行循环启动）。

- ``GET /healthz`` → 200 ``{"status":"UP","workerId":...}``（进程存活）
- ``GET /readyz``  → 200 ``{"status":"UP","db":true,"oldestQueuedJobAgeSeconds":N|null}``
  单查询 MIN(available_at) over status='queued'（进程活着 ≠ 任务在推进，
  ARCH 11.2：心跳 + 最老待办年龄共同判断）。DB 不可达 → 503 ``{"status":"DOWN"}``。
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sqlalchemy import Engine, text

from ..config import WorkerConfig
from ..logging_setup import mlog

log = logging.getLogger("mvp_worker.health")

_OLDEST_QUEUED_AGE = text(
    """
SELECT CASE
         WHEN MIN(available_at) IS NULL THEN NULL
         ELSE GREATEST(
           0,
           FLOOR(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(available_at))))
         )::bigint
       END AS age_seconds
FROM async_jobs
WHERE status = 'queued'
"""
)


def oldest_queued_age_seconds(engine: Engine) -> "int | None":
    """最老到期待办年龄（秒，向下取整，≥0）；无 queued 任务 → None。"""
    with engine.connect() as conn:
        row = conn.execute(_OLDEST_QUEUED_AGE).mappings().first()
    if row is None or row["age_seconds"] is None:
        return None
    return int(row["age_seconds"])


class _HealthServer(ThreadingHTTPServer):
    """daemon_threads=True：进程退出时健康线程不阻塞收尾。"""

    daemon_threads = True
    engine: Engine
    worker_id: str


class _Handler(BaseHTTPRequestHandler):
    server_version = "mvp_worker_health"

    @property
    def _ctx(self) -> "_HealthServer":
        return self.server  # type: ignore[return-value]

    def log_message(self, format: str, *args: object) -> None:  # 静音默认 stderr 访问日志
        return

    def _json(self, status: int, body: dict[str, object]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 (stdlib 命名约定)
        srv = self._ctx
        if self.path == "/healthz":
            self._json(200, {"status": "UP", "workerId": srv.worker_id})
        elif self.path == "/readyz":
            try:
                age = oldest_queued_age_seconds(srv.engine)
            except Exception as exc:
                mlog(log, logging.ERROR, "health.readyz_db_error",
                     workerId=srv.worker_id, errorClass=type(exc).__name__)
                self._json(503, {"status": "DOWN"})
                return
            self._json(200, {
                "status": "UP",
                "db": True,
                "oldestQueuedJobAgeSeconds": age,
            })
        else:
            self._json(404, {"status": "UP", "error": "notFound"})


def start_health_server(config: WorkerConfig, engine: Engine) -> _HealthServer:
    """在配置端口启动守护线程 HTTP 服务；调用方 shutdown()+server_close() 停止。"""
    server = _HealthServer((config.health_host, config.health_port), _Handler)
    server.engine = engine
    server.worker_id = config.worker_id
    thread = threading.Thread(
        target=server.serve_forever, name="mvp-health", daemon=True
    )
    thread.start()
    mlog(log, logging.INFO, "health.started",
         workerId=config.worker_id, port=config.health_port)
    return server
