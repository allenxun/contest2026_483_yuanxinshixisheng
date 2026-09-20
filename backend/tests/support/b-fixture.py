#!/usr/bin/env python3
"""L6 验收辅助：通知/扫描/心跳场景的真实 PG 种子与状态变更。
连接串取 MVP_WORKER_PG_DSN。每个子命令打印单行 JSON。

子命令：
  episode-gimbal --bound 0|1 --dest none|active|invalid --episode none|device|offline
                 [--binding-rev N] [--dest-rev N] [--installation X] [--code overheat]
  pending-notification --gimbal G --account A --dest D --binding-rev B --dest-rev R
                       [--incident ID] [--status pending] [--attempt N]
  unbind --gimbal G
  switch-dest --dest D --account A
  set-job --job J [--status running] [--lease-expired] [--attempt N]
  query --sql "SELECT ..."   # 仅调试
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

from sqlalchemy import text

from mvp_worker.config import WorkerConfig
from mvp_worker.db import create_db_engine

PUSH_TEXT = "云台状态异常，请查看"


def _engine():
    import os

    dsn = os.environ["MVP_WORKER_PG_DSN"]
    return create_db_engine(dsn, pool_size=2, max_overflow=0)


def _episode(incident_id: str, code: str, state: str = "active", source: str = "device") -> dict:
    return {
        incident_id: {
            "source": source,
            "code": code,
            "severity": "high" if source == "device" else None,
            "opened_at": "2026-09-11T10:00:00Z",
            "last_reported_at": "2026-09-11T10:00:00Z",
            "state": state,
            "resolved_at": None,
        }
    }


def cmd_episode_gimbal(args: argparse.Namespace) -> int:
    engine = _engine()
    try:
        account_id = None
        if args.bound:
            account_id = uuid.uuid4()
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO accounts (id, login_provider, login_subject)"
                         " VALUES (:id,'phone',:s)"),
                    {"id": account_id, "s": "acc-" + account_id.hex},
                )
        gimbal_id = uuid.uuid4()
        incident_id = "inc-" + uuid.uuid4().hex
        if args.episode == "offline":
            conn_status, last_seen = "online", True
            episodes = {}
        elif args.episode == "device":
            conn_status, last_seen = "online", False
            episodes = _episode(incident_id, args.code)
        else:
            conn_status, last_seen = "online", False
            episodes = {}
        incidents = {"schema_version": 1, "episodes": episodes}
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version,"
                    " bound_account_id, binding_revision, bound_at, connection_status,"
                    " status_revision, latest_observation, active_incidents, last_seen_at)"
                        " VALUES (:id,:serial,:auth,1,:acct,:brev,"
                        " CASE WHEN CAST(:acct AS uuid) IS NULL THEN NULL ELSE now() END,"
                    " :status,1,'{}'::jsonb, CAST(:inc AS jsonb),"
                    " CASE WHEN :old THEN now() - interval '3600 seconds' ELSE now() END)"
                ),
                {
                    "id": gimbal_id,
                    "serial": "G-FX-" + gimbal_id.hex,
                    "auth": "A-FX-" + gimbal_id.hex,
                    "acct": account_id,
                    "brev": args.binding_rev,
                    "status": conn_status,
                    "inc": json.dumps(incidents, ensure_ascii=False),
                    "old": last_seen,
                },
            )
            dest_id = None
            if args.dest != "none" and account_id is not None:
                dest_id = uuid.uuid4()
                conn.execute(
                    text(
                        "INSERT INTO notification_destinations (id, installation_id, account_id,"
                        " destination_revision, provider, platform, registration, status,"
                        " session_ref, last_registered_at)"
                        " VALUES (:id,:inst,:acct,:rev,'dev-fcm','android',"
                        " CAST(:reg AS jsonb), :status,:sref, now())"
                    ),
                    {
                        "id": dest_id,
                        "inst": args.installation or ("inst-fx-" + dest_id.hex),
                        "acct": account_id,
                        "rev": args.dest_rev,
                        "reg": json.dumps({"schema_version": 1, "token": "dev-token"}),
                        "status": args.dest if args.dest == "active" else "invalid",
                        "sref": "sess-" + dest_id.hex,
                    },
                )
        print(json.dumps({
            "accountId": None if account_id is None else str(account_id),
            "gimbalId": str(gimbal_id),
            "destinationId": None if dest_id is None else str(dest_id),
            "incidentId": incident_id,
            "installationId": args.installation,
        }))
        return 0
    finally:
        engine.dispose()


def cmd_pending_notification(args: argparse.Namespace) -> int:
    engine = _engine()
    try:
        notification_id = uuid.uuid4()
        incident_id = args.incident or ("inc-n-" + uuid.uuid4().hex)
        payload = {
            "schema_version": 1,
            "event_type": "device_incident",
            "incident_id": incident_id,
            "gimbal_id": args.gimbal,
            "text": PUSH_TEXT,
        }
        job_id = uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO notifications (id, gimbal_id, incident_id, event_type,"
                    " account_id, binding_revision, destination_id, destination_revision,"
                    " payload, status, attempt_count)"
                    " VALUES (:id,:gid,:iid,'device_incident',:acct,:brev,:did,:drev,"
                    " CAST(:payload AS jsonb), :status, :attempt)"
                ),
                {
                    "id": notification_id, "gid": args.gimbal, "iid": incident_id,
                    "acct": args.account, "brev": args.binding_rev, "did": args.dest,
                    "drev": args.dest_rev, "payload": json.dumps(payload, ensure_ascii=False),
                    "status": args.status, "attempt": args.attempt,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO async_jobs (id, job_type, dedup_key, owner_type, owner_id,"
                    " input_revision, payload, status, available_at, attempt_count, max_attempts,"
                    " lease_revision)"
                    " VALUES (:id,'notification.deliver',:dedup,'notification',:owner,"
                    " :irev, CAST(:payload AS jsonb),'queued', now(), 0, :maxatt, 0)"
                ),
                {
                    "id": job_id, "dedup": "notification:" + str(notification_id),
                    "owner": notification_id, "irev": args.dest_rev,
                    "payload": json.dumps({"schema_version": 1,
                                           "notification_id": str(notification_id)}),
                    "maxatt": WorkerConfig().retry_max_attempts,
                },
            )
        print(json.dumps({"notificationId": str(notification_id), "jobId": str(job_id),
                          "incidentId": incident_id}))
        return 0
    finally:
        engine.dispose()


def cmd_unbind(args: argparse.Namespace) -> int:
    engine = _engine()
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("UPDATE gimbals SET bound_account_id=NULL, bound_at=NULL,"
                     " binding_revision=binding_revision+1, updated_at=now()"
                     " WHERE id=:id RETURNING binding_revision"),
                {"id": args.gimbal},
            ).first()
        print(json.dumps({"bindingRevision": None if row is None else row[0]}))
        return 0
    finally:
        engine.dispose()


def cmd_switch_dest(args: argparse.Namespace) -> int:
    engine = _engine()
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("UPDATE notification_destinations SET account_id=:acct,"
                     " destination_revision=destination_revision+1, status='active',"
                     " invalidated_at=NULL, session_ref=:sref, last_registered_at=now(),"
                     " updated_at=now() WHERE id=:id RETURNING destination_revision"),
                {"acct": args.account, "id": args.dest, "sref": "sess-" + uuid.uuid4().hex},
            ).first()
        print(json.dumps({"destinationRevision": None if row is None else row[0]}))
        return 0
    finally:
        engine.dispose()


def cmd_set_job(args: argparse.Namespace) -> int:
    engine = _engine()
    try:
        sets = []
        params: dict[str, object] = {"id": args.job}
        if args.status:
            sets.append("status=:status")
            params["status"] = args.status
        if args.lease_expired:
            sets.append("lease_owner='ghost-worker'")
            sets.append("lease_until=now() - interval '1 hour'")
        if args.attempt is not None:
            sets.append("attempt_count=:attempt")
            params["attempt"] = args.attempt
        sets.append("updated_at=now()")
        with engine.begin() as conn:
            conn.execute(text("UPDATE async_jobs SET " + ", ".join(sets) + " WHERE id=:id"), params)
        print(json.dumps({"ok": True}))
        return 0
    finally:
        engine.dispose()


def cmd_query(args: argparse.Namespace) -> int:
    engine = _engine()
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(args.sql)).fetchall()
        print(json.dumps([list(r) for r in rows], default=str, ensure_ascii=False))
        return 0
    finally:
        engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="b-fixture.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    eg = sub.add_parser("episode-gimbal")
    eg.add_argument("--bound", type=int, choices=[0, 1], default=1)
    eg.add_argument("--dest", choices=["none", "active", "invalid"], default="active")
    eg.add_argument("--episode", choices=["none", "device", "offline"], default="device")
    eg.add_argument("--binding-rev", type=int, default=1)
    eg.add_argument("--dest-rev", type=int, default=1)
    eg.add_argument("--installation", default=None)
    eg.add_argument("--code", default="overheat")
    eg.set_defaults(func=cmd_episode_gimbal)

    pn = sub.add_parser("pending-notification")
    pn.add_argument("--gimbal", required=True)
    pn.add_argument("--account", required=True)
    pn.add_argument("--dest", required=True)
    pn.add_argument("--binding-rev", type=int, required=True)
    pn.add_argument("--dest-rev", type=int, required=True)
    pn.add_argument("--incident", default=None)
    pn.add_argument("--status", default="pending")
    pn.add_argument("--attempt", type=int, default=0)
    pn.set_defaults(func=cmd_pending_notification)

    ub = sub.add_parser("unbind")
    ub.add_argument("--gimbal", required=True)
    ub.set_defaults(func=cmd_unbind)

    sd = sub.add_parser("switch-dest")
    sd.add_argument("--dest", required=True)
    sd.add_argument("--account", required=True)
    sd.set_defaults(func=cmd_switch_dest)

    sj = sub.add_parser("set-job")
    sj.add_argument("--job", required=True)
    sj.add_argument("--status", default=None)
    sj.add_argument("--lease-expired", action="store_true")
    sj.add_argument("--attempt", type=int, default=None)
    sj.set_defaults(func=cmd_set_job)

    q = sub.add_parser("query")
    q.add_argument("--sql", required=True)
    q.set_defaults(func=cmd_query)
    return p


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    sys.exit(parsed.func(parsed))
