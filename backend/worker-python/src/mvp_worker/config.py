"""MVP Worker 配置（env 驱动，dev 初值见 .coordination/A/decisions.md #13）。

约定：
- 运行时连接串 ``MVP_WORKER_PG_DSN``；未设置时回退 ``MVP_A_PG_DSN``
  （跨语言自检/脚本统一入口 env），再未设置默认 dev 运行库 ``mvp_a_dev``。
- ``--check`` 连通自检连接串：``MVP_A_PG_DSN``（默认隔离容器 maintenance 库
  ``postgres``，与骨架行为一致）。
- 密码只走环境变量，不写入代码或仓库。
"""
from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass, field

DEFAULT_RUNTIME_DSN = "postgresql://postgres:mvp_a_local@127.0.0.1:55432/mvp_a_dev"
DEFAULT_CHECK_DSN = "postgresql://postgres:mvp_a_local@127.0.0.1:55432/postgres"
DEFAULT_HEALTH_PORT = 8081
DEFAULT_HEALTH_HOST = "127.0.0.1"
# Worker 连接池 dev 初值（联调起点，非验收硬值）；max_overflow 固定 0
DEFAULT_POOL_SIZE = 5
DEFAULT_CLAIM_BATCH = 5
DEFAULT_LEASE_SECONDS = 60
DEFAULT_RENEW_INTERVAL_SECONDS = 15
DEFAULT_RETRY_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_BASE_SECONDS = 5
DEFAULT_BACKOFF_CAP_SECONDS = 300
DEFAULT_POLL_INTERVAL_SECONDS = 2
DEFAULT_ENVIRONMENT = "dev"
DEFAULT_STORAGE_DEV_DIR = "/tmp/mvp-a-storage"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def build_worker_id() -> str:
    """领取者标识：``{hostname}:{pid}:{uuid4hex8}``（lease_owner 列，≤128 字符）。"""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class WorkerConfig:
    # --- 数据库 ---
    runtime_dsn: str = field(default_factory=lambda: (
        os.environ.get("MVP_WORKER_PG_DSN")
        or os.environ.get("MVP_A_PG_DSN")
        or DEFAULT_RUNTIME_DSN
    ))
    check_dsn: str = field(
        default_factory=lambda: os.environ.get("MVP_A_PG_DSN", DEFAULT_CHECK_DSN)
    )
    pool_size: int = field(
        default_factory=lambda: int(os.environ.get("MVP_WORKER_POOL_SIZE", DEFAULT_POOL_SIZE))
    )
    max_overflow: int = 0  # 固定：Worker 池不外溢（decisions #13）

    # --- 领取 / 租约 / 重试（dev 初值，env 可覆盖） ---
    claim_batch: int = field(
        default_factory=lambda: _env_int("MVP_WORKER_CLAIM_BATCH", DEFAULT_CLAIM_BATCH)
    )
    lease_seconds: int = field(
        default_factory=lambda: _env_int("MVP_WORKER_LEASE_SECONDS", DEFAULT_LEASE_SECONDS)
    )
    renew_interval_seconds: int = field(
        default_factory=lambda: _env_int(
            "MVP_WORKER_RENEW_INTERVAL_SECONDS", DEFAULT_RENEW_INTERVAL_SECONDS
        )
    )
    retry_max_attempts: int = field(
        default_factory=lambda: _env_int(
            "MVP_WORKER_RETRY_MAX_ATTEMPTS", DEFAULT_RETRY_MAX_ATTEMPTS
        )
    )
    backoff_base_seconds: int = field(
        default_factory=lambda: _env_int(
            "MVP_WORKER_BACKOFF_BASE_SECONDS", DEFAULT_BACKOFF_BASE_SECONDS
        )
    )
    backoff_cap_seconds: int = field(
        default_factory=lambda: _env_int(
            "MVP_WORKER_BACKOFF_CAP_SECONDS", DEFAULT_BACKOFF_CAP_SECONDS
        )
    )
    poll_interval_seconds: int = field(
        default_factory=lambda: _env_int(
            "MVP_WORKER_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS
        )
    )

    # --- 身份 / 环境 ---
    worker_id: str = field(default_factory=build_worker_id)
    # 对象 key 前缀 environment（media key 规范 environment/purpose/random-media-id）
    environment: str = field(
        default_factory=lambda: os.environ.get("MVP_WORKER_ENVIRONMENT", DEFAULT_ENVIRONMENT)
    )

    # --- 健康端点（仅运行循环启动，--check/--once/--recover 不启动） ---
    health_host: str = field(
        default_factory=lambda: os.environ.get("MVP_WORKER_HEALTH_HOST", DEFAULT_HEALTH_HOST)
    )
    health_port: int = field(
        default_factory=lambda: int(
            os.environ.get("MVP_WORKER_HEALTH_PORT", DEFAULT_HEALTH_PORT)
        )
    )

    # --- 本地存储替身根目录（B/C/D 与测试共用布局） ---
    storage_dev_dir: str = field(
        default_factory=lambda: os.environ.get("MVP_A_STORAGE_DEV_DIR", DEFAULT_STORAGE_DEV_DIR)
    )
