"""B 包通知/扫描 pytest 共享夹具（仅测试使用；不是生产模块）。

放在 tests 目录外会被 pytest 当源码收集，因此命名为 test_notification_support
并由各 test_notification_* / test_incident_scanner* 模块 import。
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import Engine, text

from b_support import b_clean_tables  # noqa: F401  re-export：供 B 各测试模块挂载 autouse 自清
from mvp_worker.config import WorkerConfig
from mvp_worker.handlers import HandlerContext, JobFailed
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import complete_failure, complete_success
from mvp_worker.runtime.rows import JobRow

PUSH_TEXT = "云台状态异常，请查看"


def new_account_subject() -> str:
    return "notif-" + uuid.uuid4().hex


def seed_account(engine: Engine, subject: Optional[str] = None) -> uuid.UUID:
    account_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, login_provider, login_subject)"
                " VALUES (:id, 'phone', :subject)"
            ),
            {"id": account_id, "subject": subject or new_account_subject()},
        )
    return account_id


def seed_gimbal(
    engine: Engine,
    *,
    account_id: Optional[uuid.UUID] = None,
    binding_revision: int = 0,
    status: str = "online",
    last_seen_at: Optional[datetime] = None,
    episodes: Optional[dict[str, Any]] = None,
    status_revision: int = 1,
) -> uuid.UUID:
    gimbal_id = uuid.uuid4()
    incidents = {"schema_version": 1, "episodes": episodes or {}}
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version,"
                " bound_account_id, binding_revision, bound_at, connection_status,"
                " status_revision, latest_observation, active_incidents, last_seen_at)"
                " VALUES (:id, :serial, :auth, 1, :account, :brev, :bound_at, :status,"
                " :srev, '{}'::jsonb, CAST(:incidents AS jsonb), :last_seen)"
            ),
            {
                "id": gimbal_id,
                "serial": "notif-gimbal-" + gimbal_id.hex,
                "auth": "cred-" + str(gimbal_id),
                "account": account_id,
                "brev": binding_revision,
                "bound_at": datetime.now(timezone.utc) if account_id else None,
                "status": status,
                "srev": status_revision,
                "incidents": json.dumps(incidents, ensure_ascii=False),
                "last_seen": last_seen_at,
            },
        )
    return gimbal_id


def seed_destination(
    engine: Engine,
    *,
    account_id: uuid.UUID,
    revision: int = 1,
    status: str = "active",
    session_ref: str = "sess-1",
    provider: str = "dev-fcm",
    platform: str = "android",
    registration: Optional[dict[str, Any]] = None,
) -> uuid.UUID:
    destination_id = uuid.uuid4()
    reg = registration or {"schema_version": 1, "token": "dev-token"}
    installation = "notif-inst-" + destination_id.hex
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO notification_destinations"
                " (id, installation_id, account_id, destination_revision, provider, platform,"
                " registration, status, session_ref, last_registered_at)"
                " VALUES (:id, :inst, :account, :rev, :provider, :platform,"
                " CAST(:reg AS jsonb), :status, :sref, now())"
            ),
            {
                "id": destination_id,
                "inst": installation,
                "account": account_id,
                "rev": revision,
                "provider": provider,
                "platform": platform,
                "reg": json.dumps(reg, ensure_ascii=False),
                "status": status,
                "sref": session_ref,
            },
        )
    return destination_id


def device_episode(incident_id: str, code: str = "overheat", state: str = "active") -> dict[str, Any]:
    return {
        incident_id: {
            "source": "device",
            "code": code,
            "severity": "high",
            "opened_at": "2026-09-11T10:00:00Z",
            "last_reported_at": "2026-09-11T10:00:00Z",
            "state": state,
            "resolved_at": None,
        }
    }


def offset_episodes(episodes: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for iid, ep in episodes.items():
        ep = dict(ep)
        if ep.get("source") == "offline":
            base = iid
            ep["code"] = ep.get("code") or "gimbal_offline"
        out[iid] = ep
    return out


def seed_notification(
    engine: Engine,
    *,
    gimbal_id: uuid.UUID,
    incident_id: str,
    account_id: uuid.UUID,
    binding_revision: int,
    destination_id: uuid.UUID,
    destination_revision: int,
    status: str = "pending",
    attempt_count: int = 0,
    last_attempt_at: Optional[datetime] = None,
    payload: Optional[dict[str, Any]] = None,
) -> uuid.UUID:
    notification_id = uuid.uuid4()
    body = payload or {
        "schema_version": 1,
        "event_type": "device_incident",
        "incident_id": incident_id,
        "gimbal_id": str(gimbal_id),
        "text": PUSH_TEXT,
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO notifications"
                " (id, gimbal_id, incident_id, event_type, account_id, binding_revision,"
                " destination_id, destination_revision, payload, status, attempt_count,"
                " last_attempt_at)"
                " VALUES (:id, :gid, :iid, :etype, :acct, :brev, :did, :drev,"
                " CAST(:payload AS jsonb), :status, :attempt, :last_attempt)"
            ),
            {
                "id": notification_id,
                "gid": gimbal_id,
                "iid": incident_id,
                "etype": body.get("event_type", "device_incident"),
                "acct": account_id,
                "brev": binding_revision,
                "did": destination_id,
                "drev": destination_revision,
                "payload": json.dumps(body, ensure_ascii=False),
                "status": status,
                "attempt": attempt_count,
                "last_attempt": last_attempt_at,
            },
        )
    return notification_id


def enqueue_deliver_job(
    engine: Engine, notification_id: uuid.UUID, *, input_revision: int = 1, max_attempts: int = 5
) -> uuid.UUID:
    job_id = uuid.uuid4()
    payload = {"schema_version": 1, "notification_id": str(notification_id)}
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO async_jobs"
                " (id, job_type, dedup_key, owner_type, owner_id, input_revision, payload,"
                " status, available_at, attempt_count, max_attempts, lease_revision)"
                " VALUES (:id, 'notification.deliver', :dedup, 'notification', :owner,"
                " :irev, CAST(:payload AS jsonb), 'queued', now(), 0, :max_attempts, 0)"
            ),
            {
                "id": job_id,
                "dedup": "notification:" + str(notification_id),
                "owner": notification_id,
                "irev": input_revision,
                "payload": json.dumps(payload, ensure_ascii=False),
                "max_attempts": max_attempts,
            },
        )
    return job_id


def claim_one(engine: Engine, worker: str = "notif-test-worker") -> Optional[JobRow]:
    claims = claim_batch(engine, worker_id=worker, lease_seconds=60, batch_size=1)
    return claims[0] if claims else None


def run_delivery(engine: Engine, job: JobRow, handler: Any) -> tuple[Any, Optional[JobFailed]]:
    """直接以已领取的 job 调 handler 并按运行时语义完成（成功/失败）。

    失败路径与 A 的 loop 一致：透传 ``exc.business_tx``（终态失败时是 T10 同事务
    收敛回调）给 ``complete_failure``。守卫 0 行会抛 ``StaleGeneration``，调用方可
    据此断言过期领取者整体回滚。
    """
    ctx = HandlerContext(
        engine=engine,
        config=WorkerConfig(),
        job=job,
        abort_event=threading.Event(),
        extras={},
    )
    try:
        result = handler.handle(ctx, job)
    except JobFailed as exc:
        complete_failure(
            engine, job, code=exc.code, message=exc.message, retryable=exc.retryable,
            backoff_base_seconds=5, backoff_cap_seconds=300,
            business_tx=exc.business_tx,
        )
        return None, exc
    complete_success(
        engine, job, handler_result_tx=result.business_tx if result is not None else None
    )
    return result, None


def fetch_notification(engine: Engine, notification_id: uuid.UUID) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, status, attempt_count, provider_message_id, last_error::text AS last_error,"
                " account_id, destination_id, destination_revision, binding_revision"
                " FROM notifications WHERE id = :id"
            ),
            {"id": notification_id},
        ).mappings().first()
    assert row is not None
    return dict(row)


def fetch_job(engine: Engine, job_id: uuid.UUID) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, status, attempt_count, max_attempts, available_at, last_error::text AS last_error"
                " FROM async_jobs WHERE id = :id"
            ),
            {"id": job_id},
        ).mappings().first()
    assert row is not None
    return dict(row)


def fetch_gimbal(engine: Engine, gimbal_id: uuid.UUID) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT connection_status, status_revision, last_seen_at,"
                " active_incidents::text AS active_incidents FROM gimbals WHERE id = :id"
            ),
            {"id": gimbal_id},
        ).mappings().first()
    assert row is not None
    return dict(row)


def make_past(seconds: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)
