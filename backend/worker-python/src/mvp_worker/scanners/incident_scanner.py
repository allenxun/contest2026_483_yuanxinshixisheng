"""离线/异常扫描器（DD 9.5；lane-m5 第三部分；C7/C8 裁定）。

职责：把读到的 T03 事实派生为
1. **离线 episode**：``connection_status='online'`` 且 ``last_seen_at`` 早于
   阈值 → ``offline`` + 开一个 ``source:"offline"`` 的 active episode；
2. **恢复关闭**：``online`` 且存在 active 的 offline episode → 置 resolved；
3. **建通知**：对每个仍有 active episode 的云台，按当前绑定账号的 active 目标
   INSERT T10（复合唯一键去重）+ T12（``notification.deliver``）。

纪律（C7）：
- **绝不**写 ``gimbals.last_seen_at``（只有有效心跳可写），扫描器对 last_seen_at
  **只读**；只写 ``connection_status`` / ``status_revision`` / ``active_incidents``。
- 只增改 ``active_incidents`` 中 ``source:"offline"`` 的键，保留 device episode。
- 绝不写 ``bound_account_id/binding_revision/bound_at/current_assessment_*``，
  绝不写 T13，绝不整行覆盖，禁 JOIN / 关联子查询（有限次单表 SELECT/UPDATE）。

运行形态（C8）：暴露可重入纯函数 :func:`run_once(engine, settings) -> ScanReport`，
供既有 Worker 进程内周期触发（由总协调接入）；**不新增常驻进程/定时服务**，
``python -m mvp_worker.scanners --once`` 用于验证。
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..config import WorkerConfig
from ..notifications.config import NotificationSettings, load_settings

log = logging.getLogger("mvp_worker.scanner.incident")

PUSH_TEXT = "云台状态异常，请查看"  # 最小正文，绝不含成员/照片/报告/手机号/账号
_EVENT_OFFLINE = "gimbal_offline"
_EVENT_DEVICE_DEFAULT = "device_incident"


@dataclass
class ScanReport:
    """单轮扫描可观测量（纯数据；不含 payload/token）。"""

    offline_candidates: int = 0
    marked_offline: int = 0
    episodes_opened: int = 0
    episodes_reused: int = 0
    recovered_gimbals: int = 0
    episodes_resolved: int = 0
    gimbals_with_active_episodes: int = 0
    skipped_unbound: int = 0
    skipped_no_destination: int = 0
    notifications_created: int = 0
    jobs_enqueued: int = 0
    failures: int = 0
    failure_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "offline_candidates": self.offline_candidates,
            "marked_offline": self.marked_offline,
            "episodes_opened": self.episodes_opened,
            "episodes_reused": self.episodes_reused,
            "recovered_gimbals": self.recovered_gimbals,
            "episodes_resolved": self.episodes_resolved,
            "gimbals_with_active_episodes": self.gimbals_with_active_episodes,
            "skipped_unbound": self.skipped_unbound,
            "skipped_no_destination": self.skipped_no_destination,
            "notifications_created": self.notifications_created,
            "jobs_enqueued": self.jobs_enqueued,
            "failures": self.failures,
            "failure_codes": list(self.failure_codes),
        }


_SELECT_OFFLINE_CANDIDATES = text(
    """
SELECT id FROM gimbals
WHERE connection_status = 'online'
  AND last_seen_at IS NOT NULL
  AND last_seen_at < now() - make_interval(secs => :threshold)
"""
)

_SELECT_LOCK_GIMBAL = text(
    """
SELECT id, connection_status, last_seen_at, status_revision,
       active_incidents::text AS active_incidents
FROM gimbals WHERE id = :id FOR UPDATE
"""
)

_SELECT_GIMBALS_WITH_INCIDENTS = text(
    """
SELECT id, bound_account_id, binding_revision, active_incidents::text AS active_incidents
FROM gimbals WHERE active_incidents <> '{}'::jsonb
"""
)

_SELECT_RECOVERY_CANDIDATES = text(
    """
SELECT id FROM gimbals
WHERE connection_status = 'online' AND active_incidents <> '{}'::jsonb
"""
)

_SELECT_ACTIVE_DESTINATIONS = text(
    """
SELECT id, destination_revision FROM notification_destinations
WHERE account_id = :account AND status = 'active'
"""
)

_INSERT_NOTIFICATION = text(
    """
INSERT INTO notifications
    (gimbal_id, incident_id, event_type, account_id, binding_revision,
     destination_id, destination_revision, payload, status, attempt_count)
VALUES (:gimbal_id, :incident_id, :event_type, :account_id, :binding_revision,
        :destination_id, :destination_revision, CAST(:payload AS jsonb), 'pending', 0)
ON CONFLICT (gimbal_id, incident_id, binding_revision, destination_id, destination_revision)
DO NOTHING
RETURNING id
"""
)

_INSERT_JOB = text(
    """
INSERT INTO async_jobs
    (job_type, dedup_key, owner_type, owner_id, input_revision, payload,
     status, available_at, attempt_count, max_attempts, lease_revision)
VALUES ('notification.deliver', :dedup_key, 'notification', :owner_id, :input_revision,
        CAST(:payload AS jsonb), 'queued', now(), 0, :max_attempts, 0)
ON CONFLICT (dedup_key) DO NOTHING
"""
)


def run_once(engine: Engine, settings: Optional[NotificationSettings] = None) -> ScanReport:
    """执行一轮扫描；无全局状态、可重入。每行独立短事务，单行失败隔离。"""
    settings = settings or load_settings()
    report = ScanReport()
    now = datetime.now(timezone.utc)
    max_attempts = WorkerConfig().retry_max_attempts

    _mark_offline(engine, settings, now, report)
    _recover(engine, now, report)
    _create_notifications(engine, max_attempts, report)
    return report


# ---------------- 1. 离线判定 ----------------


def _mark_offline(
    engine: Engine,
    settings: NotificationSettings,
    now: datetime,
    report: ScanReport,
) -> None:
    threshold = settings.offline_threshold_seconds
    with engine.connect() as conn:
        candidates = [str(r[0]) for r in conn.execute(
            _SELECT_OFFLINE_CANDIDATES, {"threshold": threshold}
        ).all()]
    report.offline_candidates = len(candidates)

    for gimbal_id in candidates:
        try:
            with engine.begin() as conn:
                row = conn.execute(_SELECT_LOCK_GIMBAL, {"id": gimbal_id}).mappings().first()
                if row is None:
                    continue
                if row["connection_status"] != "online":
                    continue
                last_seen = row["last_seen_at"]
                if last_seen is None or last_seen >= now - timedelta(seconds=threshold):
                    continue
                incidents = _parse_object(row["active_incidents"])
                episodes = incidents.get("episodes")
                if not isinstance(episodes, dict):
                    episodes = {}
                existing = _active_offline_episode_id(episodes)
                if existing is not None:
                    report.episodes_reused += 1
                else:
                    incident_id = str(uuid.uuid4())
                    episodes[incident_id] = {
                        "source": "offline",
                        "code": _EVENT_OFFLINE,
                        "severity": None,
                        "opened_at": _rfc3339(now),
                        "last_reported_at": _rfc3339(now),
                        "state": "active",
                        "resolved_at": None,
                    }
                    report.episodes_opened += 1
                incidents["schema_version"] = incidents.get("schema_version", 1)
                incidents["episodes"] = episodes
                updated = conn.execute(
                    text(
                        "UPDATE gimbals SET connection_status = 'offline',"
                        " status_revision = status_revision + 1,"
                        " active_incidents = CAST(:incidents AS jsonb), updated_at = now()"
                        " WHERE id = :id AND status_revision = :rev"
                    ),
                    {
                        "incidents": json.dumps(incidents, ensure_ascii=False),
                        "id": gimbal_id,
                        "rev": int(row["status_revision"]),
                    },
                )
                if updated.rowcount == 1:
                    report.marked_offline += 1
        except Exception as exc:  # 单行失败隔离
            _record_failure(report, "mark_offline", gimbal_id, exc)


# ---------------- 2. 恢复关闭 ----------------


def _recover(engine: Engine, now: datetime, report: ScanReport) -> None:
    with engine.connect() as conn:
        candidates = [str(r[0]) for r in conn.execute(_SELECT_RECOVERY_CANDIDATES).all()]
    for gimbal_id in candidates:
        try:
            with engine.begin() as conn:
                row = conn.execute(_SELECT_LOCK_GIMBAL, {"id": gimbal_id}).mappings().first()
                if row is None or row["connection_status"] != "online":
                    continue
                incidents = _parse_object(row["active_incidents"])
                episodes = incidents.get("episodes")
                if not isinstance(episodes, dict):
                    continue
                resolved = 0
                for episode in episodes.values():
                    if (
                        isinstance(episode, dict)
                        and episode.get("source") == "offline"
                        and episode.get("state") == "active"
                    ):
                        episode["state"] = "resolved"
                        episode["resolved_at"] = _rfc3339(now)
                        resolved += 1
                if resolved == 0:
                    continue
                conn.execute(
                    text(
                        "UPDATE gimbals SET active_incidents = CAST(:incidents AS jsonb),"
                        " updated_at = now() WHERE id = :id AND status_revision = :rev"
                    ),
                    {
                        "incidents": json.dumps(incidents, ensure_ascii=False),
                        "id": gimbal_id,
                        "rev": int(row["status_revision"]),
                    },
                )
                report.recovered_gimbals += 1
                report.episodes_resolved += resolved
        except Exception as exc:
            _record_failure(report, "recover", gimbal_id, exc)


# ---------------- 3. 建通知 ----------------


def _create_notifications(engine: Engine, max_attempts: int, report: ScanReport) -> None:
    with engine.connect() as conn:
        gimbals = conn.execute(_SELECT_GIMBALS_WITH_INCIDENTS).mappings().all()

    for gimbal in gimbals:
        try:
            incidents = _parse_object(gimbal["active_incidents"])
            episodes = incidents.get("episodes")
            active = [
                (iid, ep)
                for iid, ep in (episodes or {}).items()
                if isinstance(ep, dict) and ep.get("state") == "active"
            ]
            if not active:
                continue
            report.gimbals_with_active_episodes += 1
            account_id = gimbal["bound_account_id"]
            if account_id is None:
                # 无绑定 → 绝不生成可投递通知（SC-00-04/SC-01-15）
                report.skipped_unbound += 1
                continue
            binding_revision = int(gimbal["binding_revision"])
            with engine.connect() as conn:
                destinations = conn.execute(
                    _SELECT_ACTIVE_DESTINATIONS, {"account": account_id}
                ).mappings().all()
            if not destinations:
                # 无有效目标 → 不建通知、不记 submitted（SC-01-18）
                report.skipped_no_destination += 1
                continue

            for incident_id, episode in active:
                event_type = episode.get("code") or (
                    _EVENT_OFFLINE if episode.get("source") == "offline"
                    else _EVENT_DEVICE_DEFAULT
                )
                for destination in destinations:
                    destination_revision = int(destination["destination_revision"])
                    payload = {
                        "schema_version": 1,
                        "event_type": event_type,
                        "incident_id": incident_id,
                        "gimbal_id": str(gimbal["id"]),
                        "text": PUSH_TEXT,
                    }
                    with engine.begin() as conn:
                        inserted = conn.execute(
                            _INSERT_NOTIFICATION,
                            {
                                "gimbal_id": gimbal["id"],
                                "incident_id": incident_id,
                                "event_type": event_type,
                                "account_id": account_id,
                                "binding_revision": binding_revision,
                                "destination_id": destination["id"],
                                "destination_revision": destination_revision,
                                "payload": json.dumps(payload, ensure_ascii=False),
                            },
                        ).first()
                        if inserted is None:
                            continue  # 复合唯一键去重（重复扫描不重复建行）
                        notification_id = inserted[0]
                        report.notifications_created += 1
                        job_payload = {
                            "schema_version": 1,
                            "notification_id": str(notification_id),
                        }
                        conn.execute(
                            _INSERT_JOB,
                            {
                                "dedup_key": "notification:" + str(notification_id),
                                "owner_id": notification_id,
                                "input_revision": destination_revision,
                                "payload": json.dumps(job_payload, ensure_ascii=False),
                                "max_attempts": max_attempts,
                            },
                        )
                        report.jobs_enqueued += 1
        except Exception as exc:
            _record_failure(report, "create_notifications", str(gimbal["id"]), exc)


# ---------------- helpers ----------------


def _active_offline_episode_id(episodes: dict[str, Any]) -> Optional[str]:
    for incident_id, episode in episodes.items():
        if (
            isinstance(episode, dict)
            and episode.get("source") == "offline"
            and episode.get("state") == "active"
        ):
            return str(incident_id)
    return None


def _parse_object(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _record_failure(report: ScanReport, stage: str, gimbal_id: str, exc: Exception) -> None:
    report.failures += 1
    report.failure_codes.append(f"{stage}:{type(exc).__name__}")
    # 只记阶段/类型/id，绝不记 payload/token。
    log.warning(
        "scanner.row_failure",
        extra={"stage": stage, "gimbalId": gimbal_id, "errorClass": type(exc).__name__},
    )
