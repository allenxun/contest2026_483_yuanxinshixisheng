"""A 包骨架自检（不依赖 PG；真实连接验证走 `python -m mvp_worker --check`）。"""
import json
import logging
import re

from mvp_worker import __version__
from mvp_worker.config import (
    DEFAULT_CHECK_DSN,
    DEFAULT_RUNTIME_DSN,
    WorkerConfig,
)
from mvp_worker.logging_setup import JsonFormatter, mlog


def test_version_present() -> None:
    assert __version__ == "0.0.1"


def test_config_defaults() -> None:
    cfg = WorkerConfig()
    assert cfg.check_dsn == DEFAULT_CHECK_DSN
    assert cfg.runtime_dsn == DEFAULT_RUNTIME_DSN
    assert cfg.pool_size == 5
    assert cfg.health_port == 8081


def test_config_lease_and_retry_defaults() -> None:
    cfg = WorkerConfig()
    assert cfg.max_overflow == 0
    assert cfg.claim_batch == 5
    assert cfg.lease_seconds == 60
    assert cfg.renew_interval_seconds == 15
    assert cfg.retry_max_attempts == 5
    assert cfg.backoff_base_seconds == 5
    assert cfg.backoff_cap_seconds == 300
    assert cfg.poll_interval_seconds == 2
    assert cfg.environment == "dev"
    assert cfg.storage_dev_dir == "/tmp/mvp-a-storage"
    # worker_id = hostname:pid:uuid4hex8
    assert re.fullmatch(r".+:\d+:[0-9a-f]{8}", cfg.worker_id)


def test_structured_log_fields_and_no_payload_leak() -> None:
    logger = logging.getLogger("mvp_worker.sanity")
    record = logger.makeRecord(
        "t", logging.INFO, "f.py", 1, "job.claimed", (), None
    )
    mlog_fields = {"workerId": "w", "jobId": "j", "jobType": "system.echo",
                   "dedupKey": "k", "leaseRevision": 3, "attemptCount": 1,
                   "inputRevision": 0}
    record._mvp = mlog_fields  # type: ignore[attr-defined]
    entry = json.loads(JsonFormatter().format(record))
    assert entry["event"] == "job.claimed"
    assert entry["level"] == "INFO"
    assert entry["leaseRevision"] == 3
    assert entry["jobType"] == "system.echo"
    assert "payload" not in entry  # 契约：无 payload 字段
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", entry["ts"])
