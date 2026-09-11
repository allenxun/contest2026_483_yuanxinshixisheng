"""Python 必测 13/17/18：无绑定/无目标不建通知、离线 episode 稳定性与恢复、
从未心跳不判离线（真实 PG @55435）。"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import Engine, text
from test_notification_support import (
    device_episode,
    fetch_gimbal,
    make_past,
    seed_account,
    seed_destination,
    seed_gimbal,
)

from mvp_worker.notifications.config import NotificationSettings
from mvp_worker.scanners.incident_scanner import run_once


def _settings() -> NotificationSettings:
    return NotificationSettings(offline_threshold_seconds=60)


def _episodes_of(gimbal_row) -> dict:
    return json.loads(gimbal_row["active_incidents"]).get("episodes", {})


def _online_episodes(episodes: dict) -> list:
    return [ep for ep in episodes.values() if ep.get("state") == "active"]


def _notification_count(engine: Engine, gimbal_id: uuid.UUID) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM notifications WHERE gimbal_id = :id"), {"id": gimbal_id}
        ).scalar_one()


# ---------------- 17. episode 稳定性 ----------------


def test_offline_episode_stable_then_recovery_new_id(engine: Engine) -> None:
    account = seed_account(engine)
    gimbal = seed_gimbal(
        engine, account_id=account, binding_revision=1, status="online",
        last_seen_at=make_past(3600), episodes={},
    )
    seed_destination(engine, account_id=account, revision=1, session_ref="sess-1")

    first = run_once(engine, _settings())
    assert first.marked_offline == 1
    assert first.episodes_opened == 1
    assert _notification_count(engine, gimbal) == 1
    assert first.jobs_enqueued >= 1

    row = fetch_gimbal(engine, gimbal)
    assert row["connection_status"] == "offline"
    active = _online_episodes(_episodes_of(row))
    assert len(active) == 1
    incident_id = next(iter(_episodes_of(row)))
    assert _episodes_of(row)[incident_id]["source"] == "offline"

    # 第二轮：复合唯一键 + episode 复用，不产生新 episode / 新通知
    run_once(engine, _settings())
    assert _notification_count(engine, gimbal) == 1
    row = fetch_gimbal(engine, gimbal)
    assert list(_episodes_of(row).keys()) == [incident_id]
    assert len(_online_episodes(_episodes_of(row))) == 1

    # 心跳恢复（模拟 M2-A02：online + last_seen 刷新）→ 关闭 offline episode
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE gimbals SET connection_status = 'online', last_seen_at = now()"
                 " WHERE id = :id"),
            {"id": gimbal},
        )
    third = run_once(engine, _settings())
    assert third.episodes_resolved == 1
    episodes = _episodes_of(fetch_gimbal(engine, gimbal))
    assert episodes[incident_id]["state"] == "resolved"
    assert episodes[incident_id]["resolved_at"]

    # 再次过期 → 新 incidentId，并新建第二条通知
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE gimbals SET connection_status = 'online', last_seen_at = :old"
                 " WHERE id = :id"),
            {"old": make_past(3600), "id": gimbal},
        )
    fourth = run_once(engine, _settings())
    assert fourth.episodes_opened == 1
    new_episodes = _episodes_of(fetch_gimbal(engine, gimbal))
    new_active_id = next(
        iid for iid, ep in new_episodes.items()
        if ep.get("source") == "offline" and ep.get("state") == "active"
    )
    assert new_active_id != incident_id
    assert _notification_count(engine, gimbal) == 2


# ---------------- 18. 从未心跳不判离线 ----------------


def test_never_heartbeat_never_offline(engine: Engine) -> None:
    account = seed_account(engine)
    never = seed_gimbal(
        engine, account_id=account, binding_revision=1, status="unknown",
        last_seen_at=None, episodes={},
    )
    unknown_but_seen = seed_gimbal(
        engine, account_id=account, binding_revision=1, status="unknown",
        last_seen_at=make_past(3600), episodes={},
    )
    seed_destination(engine, account_id=account, revision=1, session_ref="sess-1")

    report = run_once(engine, _settings())

    assert report.marked_offline == 0
    assert fetch_gimbal(engine, never)["connection_status"] == "unknown"
    assert fetch_gimbal(engine, unknown_but_seen)["connection_status"] == "unknown"
    assert _notification_count(engine, never) == 0
    assert _notification_count(engine, unknown_but_seen) == 0


# ---------------- 13. 无绑定 / 无目标不建通知 ----------------


def test_unbound_gimbal_gets_no_notification(engine: Engine) -> None:
    incident = str(uuid.uuid4())
    gimbal = seed_gimbal(
        engine, account_id=None, binding_revision=0, status="online",
        last_seen_at=make_past(3600), episodes=device_episode(incident),
    )
    report = run_once(engine, _settings())

    assert report.skipped_unbound >= 1
    assert _notification_count(engine, gimbal) == 0
    with engine.connect() as conn:
        submitted = conn.execute(
            text("SELECT count(*) FROM notifications WHERE gimbal_id = :id"
                 " AND status = 'submitted'"),
            {"id": gimbal},
        ).scalar_one()
    assert submitted == 0


def test_bound_without_active_destination_gets_no_notification(engine: Engine) -> None:
    account = seed_account(engine)
    incident = str(uuid.uuid4())
    gimbal = seed_gimbal(
        engine, account_id=account, binding_revision=1, status="online",
        last_seen_at=make_past(3600), episodes=device_episode(incident),
    )
    report = run_once(engine, _settings())

    assert report.skipped_no_destination >= 1
    assert _notification_count(engine, gimbal) == 0
    with engine.connect() as conn:
        submitted = conn.execute(
            text("SELECT count(*) FROM notifications WHERE gimbal_id = :id"
                 " AND status = 'submitted'"),
            {"id": gimbal},
        ).scalar_one()
    assert submitted == 0
