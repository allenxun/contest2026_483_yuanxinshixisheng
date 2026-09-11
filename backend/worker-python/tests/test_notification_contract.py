"""Python 必测 21/22：payload 契约校验与运行时 UNSUPPORTED_CONTRACT、注册表、
生产 fail-closed（真实 PG @55435）。"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import Engine, text

from b_support import b_clean_tables  # noqa: F401  autouse B 自清
from mvp_worker.config import WorkerConfig
from mvp_worker.handlers import UnsupportedPayload, get_handler, registered_job_types
from mvp_worker.handlers.notification_deliver import NotificationDeliverHandler
from mvp_worker.notifications.config import NotificationSettings
from mvp_worker.notifications.push import build_push_provider
from mvp_worker.notifications.session_probe import build_session_probe
from mvp_worker.runtime.loop import WorkerRuntime

_GOOD = {"schema_version": 1, "notification_id": str(uuid.uuid4())}


def test_validate_accepts_minimal_payload() -> None:
    NotificationDeliverHandler().validate(dict(_GOOD))


@pytest.mark.parametrize(
    "bad",
    [
        {"schema_version": 1},                                  # 缺 notification_id
        {"notification_id": str(uuid.uuid4())},                 # 缺 schema_version
        {"schema_version": 1, "notification_id": str(uuid.uuid4()), "extra": 1},  # 多字段
        {"schema_version": "1", "notification_id": str(uuid.uuid4())},  # 版本是字符串
        {"schema_version": 2, "notification_id": str(uuid.uuid4())},    # 版本 2
        "not-an-object",
    ],
)
def test_validate_rejects_bad_payload(bad) -> None:
    with pytest.raises(UnsupportedPayload):
        NotificationDeliverHandler().validate(bad)


def _enqueue_bad_job(engine: Engine, payload: dict) -> uuid.UUID:
    job_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO async_jobs"
                " (id, job_type, dedup_key, owner_type, owner_id, input_revision, payload,"
                " status, available_at, attempt_count, max_attempts, lease_revision)"
                " VALUES (:id, 'notification.deliver', :dedup, 'notification', :owner,"
                " 1, CAST(:payload AS jsonb), 'queued', now(), 0, 5, 0)"
            ),
            {
                "id": job_id,
                "dedup": "notification:" + str(job_id),
                "owner": job_id,
                "payload": json.dumps(payload),
            },
        )
    return job_id


def test_runtime_marks_unsupported_contract_without_retry(engine: Engine) -> None:
    # schema_version=2 是合法 JSONB 数字（过 DB CHECK）但违反 payload 契约 const 1。
    job_id = _enqueue_bad_job(engine, {"schema_version": 2, "notification_id": str(uuid.uuid4())})

    runtime = WorkerRuntime(WorkerConfig(), engine=engine)
    runtime.run_cycle()

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, attempt_count, last_error::text AS last_error"
                 " FROM async_jobs WHERE id = :id"),
            {"id": job_id},
        ).mappings().one()
    assert row["status"] == "failed"
    assert row["attempt_count"] == 1
    err = json.loads(row["last_error"])
    assert err["code"] == "UNSUPPORTED_CONTRACT"
    assert err["retryable"] is False

    # 再跑一轮不得再领取/重试（不进入重试循环）。
    runtime.run_cycle()
    with engine.connect() as conn:
        after = conn.execute(
            text("SELECT attempt_count FROM async_jobs WHERE id = :id"), {"id": job_id}
        ).scalar_one()
    assert after == 1


def test_registry_contains_notification_and_system() -> None:
    types = registered_job_types()
    assert "notification.deliver" in types
    assert "system.echo" in types
    assert get_handler("notification.deliver") is not None


def test_production_fail_closed() -> None:
    prod = NotificationSettings(environment="production")
    with pytest.raises(RuntimeError):
        build_push_provider(prod)


def test_production_session_probe_fail_closed(engine: Engine) -> None:
    prod = NotificationSettings(environment="production")
    with pytest.raises(RuntimeError):
        build_session_probe(engine, prod)
