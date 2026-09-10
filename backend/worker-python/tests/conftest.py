"""pytest fixtures：真实 PG（隔离容器 mvp-a-pg）+ Flyway 迁移的临时库。

会话级：CREATE DATABASE mvp_a_test_p_<uuid>（连 maintenance 库）→
bash backend/deploy/dev/migrate.sh <dbname>（只读使用，Flyway 唯一迁移入口）→
yield DSN → DROP DATABASE … WITH (FORCE)。
测试间清表（async_jobs / media_objects），不跨测试串数据。
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Optional

import psycopg
import pytest
from sqlalchemy import Engine, text

from mvp_worker.config import WorkerConfig
from mvp_worker.db import create_db_engine

WORKER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_DIR.parents[1]
MIGRATE_SH = REPO_ROOT / "backend" / "deploy" / "dev" / "migrate.sh"
CONTRACTS_DIR = REPO_ROOT / "backend" / "contracts"

# maintenance DSN：与 --check 同源（MVP_A_PG_DSN），默认隔离容器 55432
MAINT_DSN = os.environ.get(
    "MVP_A_PG_DSN", "postgresql://postgres:mvp_a_local@127.0.0.1:55432/postgres"
)

# decisions #4 / contracts/decisions-notes.md：跨语言共享的固定命名空间
FIXED_NS = uuid.UUID("f988d041-6031-5120-8075-f90b6b05553e")


def echo_owner_id(dedup_key: str) -> uuid.UUID:
    """system job 的 owner_id = UUIDv5(FIXED_NS, dedup_key)（与 Java 侧一致）。"""
    return uuid.uuid5(FIXED_NS, dedup_key)


def default_echo_payload() -> dict[str, Any]:
    path = CONTRACTS_DIR / "samples" / "jobs" / "system-echo.json"
    return json.loads(path.read_text(encoding="utf-8"))


_INSERT_JOB = text(
    """
INSERT INTO async_jobs (job_type, dedup_key, owner_type, owner_id, input_revision,
                        payload, status, available_at, attempt_count, max_attempts)
VALUES (:job_type, :dedup_key, :owner_type, :owner_id, :input_revision,
        CAST(:payload AS jsonb), 'queued',
        CURRENT_TIMESTAMP + make_interval(secs => :delay_seconds),
        0, :max_attempts)
ON CONFLICT (dedup_key) DO NOTHING
RETURNING id
"""
)

_SELECT_BY_DEDUP = text("SELECT id FROM async_jobs WHERE dedup_key = :k")


def enqueue(
    engine: Engine,
    *,
    job_type: str = "system.echo",
    dedup_key: Optional[str] = None,
    owner_type: str = "system",
    owner_id: Optional[str] = None,
    input_revision: int = 0,
    payload: Optional[dict[str, Any]] = None,
    available_at_delay_seconds: Optional[float] = None,  # 相对 now 的偏移（正值=未来）
    # 默认镜像 Java app.jobs.max-attempts（JOB_MAX_ATTEMPTS，见 WorkerConfig.retry_max_attempts）
    max_attempts: int = WorkerConfig().retry_max_attempts,
) -> tuple[str, bool]:
    """镜像 Java JobEnqueuer 的去重语义：dedup_key 冲突 = 同一逻辑任务重放，
    返回既有 id（不是错误）。返回 (job_id, replayed)。"""
    if dedup_key is None:
        dedup_key = f"system:echo:{uuid.uuid4()}"
    if owner_id is None:
        owner_id = str(echo_owner_id(dedup_key))
    if payload is None:
        payload = default_echo_payload()
    with engine.begin() as conn:
        row = conn.execute(
            _INSERT_JOB,
            {
                "job_type": job_type,
                "dedup_key": dedup_key,
                "owner_type": owner_type,
                "owner_id": owner_id,
                "input_revision": input_revision,
                "payload": json.dumps(payload, ensure_ascii=False),
                "delay_seconds": (
                    0 if available_at_delay_seconds is None else float(available_at_delay_seconds)
                ),
                "max_attempts": max_attempts,
            },
        ).first()
        if row is None:
            existing = conn.execute(_SELECT_BY_DEDUP, {"k": dedup_key}).first()
            assert existing is not None
            return str(existing[0]), True
    return str(row[0]), False


def fetch_job(engine: Engine, job_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, job_type, status, lease_owner, lease_until, lease_revision,"
                " attempt_count, max_attempts, available_at, last_error, finished_at,"
                " input_revision, dedup_key"
                " FROM async_jobs WHERE id = :id"
            ),
            {"id": job_id},
        ).mappings().first()
    assert row is not None, f"job {job_id} not found"
    return dict(row)


@pytest.fixture(scope="session")
def test_dsn() -> Any:
    try:
        with psycopg.connect(MAINT_DSN, autocommit=True) as cur:
            pass
    except psycopg.OperationalError as exc:
        pytest.exit(
            f"隔离 PG（mvp-a-pg, 127.0.0.1:55432）不可达：{exc}\n"
            "先运行 backend/deploy/dev/pg-up.sh",
            returncode=1,
        )
    dbname = f"mvp_a_test_p_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(MAINT_DSN, autocommit=True) as cur:
        cur.execute(f'CREATE DATABASE "{dbname}"')
    subprocess.run(["bash", str(MIGRATE_SH), dbname], check=True)
    dsn = MAINT_DSN.rsplit("/", 1)[0] + f"/{dbname}"
    yield dsn
    with psycopg.connect(MAINT_DSN, autocommit=True) as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')


@pytest.fixture(scope="session")
def engine(test_dsn: str) -> Any:
    eng = create_db_engine(test_dsn, pool_size=5, max_overflow=0)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean_tables(engine: Engine) -> Any:
    """逐测试清空 Worker 可写表，保证隔离。"""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM async_jobs"))
        conn.execute(text("DELETE FROM media_objects"))
    yield
