"""D 包测试支撑：真实 PG 业务表 seed / FK 安全清理 / handler 运行助手。

不修改 tests/conftest.py；本模块只做 D 任务自己的业务表（T01/T03/T04/T05/T06/T11）
seed 与清理，以及直接调用 handler + runtime 完成/失败写回的测试运行器。
"""
from __future__ import annotations

import base64
import json
import threading
import uuid
from typing import Any, Optional

from sqlalchemy import Engine, text

from mvp_worker.config import WorkerConfig
from mvp_worker.handlers import HandlerContext, JobFailed
from mvp_worker.handlers.dshared.constants import (
    candidate_entity_id,
    namespace_owner_id,
)
from mvp_worker.handlers.dshared.dconfig import DEFAULT_PLAN_CAPABILITY_BASELINE
from mvp_worker.media.storage import build_object_key
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import complete_deferred, complete_failure, complete_success
from mvp_worker.runtime.expire import release_claim
from mvp_worker.runtime.rows import JobRow

FIXED_NS = uuid.UUID("f988d041-6031-5120-8075-f90b6b05553e")
DEFAULT_NS = "mvp-ns-1"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
VIEWS = ("front", "left", "right")


# ---------------------------------------------------------------- cleanup


def clean_d_tables(engine: Engine) -> None:
    """FK 安全顺序清理 D 会 seed 的业务表（同会话测试隔离）。"""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM care_records"))
        conn.execute(text("DELETE FROM care_executions"))
        conn.execute(text("DELETE FROM care_plans"))
        conn.execute(text("DELETE FROM media_objects"))
        # 报告发布行不允许 member_id 为空；先脱离 report_ready 再解除成员引用
        conn.execute(
            text(
                "UPDATE skin_assessments SET status = 'failed', member_id = NULL"
                " WHERE status = 'report_ready'"
            )
        )
        conn.execute(text("UPDATE skin_assessments SET member_id = NULL"))
        conn.execute(text("DELETE FROM members"))
        conn.execute(text("UPDATE gimbals SET current_assessment_id = NULL"))
        conn.execute(text("DELETE FROM skin_assessments"))
        conn.execute(text("DELETE FROM microcrystals"))
        conn.execute(text("DELETE FROM gimbals"))
        conn.execute(text("DELETE FROM accounts"))
        conn.execute(text("DELETE FROM idempotency_requests"))


# ---------------------------------------------------------------- seeds


def seed_idempotency(
    engine: Engine,
    *,
    status: str = "processing",
    lease_until_seconds: Optional[float] = None,
    verification_summary: Optional[dict[str, Any]] = None,
    result_summary: Optional[dict[str, Any]] = None,
) -> str:
    iid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO idempotency_requests (id, principal_type, principal_id,"
                " operation, idempotency_key, payload_hash, status, lease_until,"
                " verification_summary, result_summary)"
                " VALUES (CAST(:id AS uuid), 'app_account', :pid, 'test', :ik, 'hash',"
                " :status, CASE WHEN CAST(:lease AS double precision) IS NULL THEN NULL"
                " ELSE CURRENT_TIMESTAMP + make_interval(secs => CAST(:lease AS double precision)) END,"
                " CAST(:vs AS jsonb), CAST(:rs AS jsonb))"
            ),
            {
                "id": iid,
                "pid": str(uuid.uuid4()),
                "ik": str(uuid.uuid4()),
                "status": status,
                "lease": lease_until_seconds,
                "vs": _json(verification_summary or {}),
                "rs": _json(result_summary or {}),
            },
        )
    return iid


def seed_account(engine: Engine) -> str:
    aid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, login_provider, login_subject)"
                " VALUES (CAST(:id AS uuid), 'test', :sub)"
            ),
            {"id": aid, "sub": f"acct-{uuid.uuid4().hex[:12]}"},
        )
    return aid


def seed_gimbal(engine: Engine) -> str:
    gid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gimbals (id, serial_no, auth_subject_ref)"
                " VALUES (CAST(:id AS uuid), :sn, :ref)"
            ),
            {"id": gid, "sn": f"gimbal-{uuid.uuid4().hex[:8]}",
             "ref": f"auth-{uuid.uuid4().hex[:8]}"},
        )
    return gid


def seed_assessment(
    engine: Engine,
    *,
    gimbal_id: Optional[str] = None,
    assessment_id: Optional[str] = None,
    status: str = "queued",
    current_photo_version: int = 1,
    processing_revision: int = 0,
    photo_versions: Optional[dict[str, Any]] = None,
    member_id: Optional[str] = None,
    source_request_id: Optional[str] = None,
) -> str:
    aid = assessment_id or str(uuid.uuid4())
    gid = gimbal_id or seed_gimbal(engine)
    srid = source_request_id or seed_idempotency(engine)
    pv = photo_versions if photo_versions is not None else {"schema_version": 1, "versions": []}
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO skin_assessments (id, gimbal_id, member_id, status,"
                " current_photo_version, processing_revision, photo_versions, source_request_id)"
                " VALUES (CAST(:id AS uuid), CAST(:gid AS uuid), CAST(:mid AS uuid), :status,"
                " :cpv, :prev, CAST(:pv AS jsonb), CAST(:srid AS uuid))"
            ),
            {
                "id": aid,
                "gid": gid,
                "mid": member_id,
                "status": status,
                "cpv": int(current_photo_version),
                "prev": int(processing_revision),
                "pv": _json(pv),
                "srid": srid,
            },
        )
    return aid


def photo_versions_for(
    version: int,
    images: dict[str, str],
    *,
    quality_status: str = "accepted",
    required_views: Optional[list[str]] = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "versions": [
            {
                "version": version,
                "images": dict(images),
                "quality": {
                    "status": quality_status,
                    "required_views": list(required_views or []),
                },
            }
        ],
    }


def seed_source_media(
    engine: Engine,
    storage: Any,
    *,
    assessment_id: str,
    photo_version: int,
    environment: str = "dev",
) -> dict[str, str]:
    ids: dict[str, str] = {}
    for view in VIEWS:
        mid = str(uuid.uuid4())
        key = build_object_key(environment, "assessment_source", mid)
        storage.put(key, PNG_BYTES)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO media_objects (id, bucket, object_key, purpose,"
                    " assessment_id, photo_version, state, content_type, byte_size,"
                    " content_hash, uploader_type)"
                    " VALUES (CAST(:id AS uuid), 'mvp-media', :k, 'assessment_source',"
                    " CAST(:a AS uuid), :pv, 'available', 'image/png', :bs, :h, 'worker')"
                ),
                {
                    "id": mid,
                    "k": key,
                    "a": assessment_id,
                    "pv": int(photo_version),
                    "bs": len(PNG_BYTES),
                    "h": "0" * 64,
                },
            )
        ids[view] = mid
    return ids


def seed_member(
    engine: Engine,
    *,
    ns: str = DEFAULT_NS,
    ref: Optional[str] = None,
    assessment_id: Optional[str] = None,
    identity_summary: Optional[dict[str, Any]] = None,
) -> str:
    mid = str(uuid.uuid4())
    summary = identity_summary if identity_summary is not None else {"schema_version": 1}
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO members (id, identity_namespace, face_subject_ref, profile,"
                " identity_summary, created_from_assessment_id, status)"
                " VALUES (CAST(:id AS uuid), :ns, :ref, '{}'::jsonb,"
                " CAST(:summary AS jsonb), CAST(:a AS uuid), 'active')"
            ),
            {
                "id": mid,
                "ns": ns,
                "ref": ref or str(uuid.uuid4()),
                "summary": _json(summary),
                "a": assessment_id,
            },
        )
    return mid


def seed_microcrystal(
    engine: Engine,
    *,
    capability_id: str = "mvp-double-capability",
    revision: Any = 1,
    observed_offset_seconds: Optional[float] = 0.0,
    observation: Optional[dict[str, Any]] = None,
    parameter_ranges: Optional[dict[str, Any]] = None,
) -> str:
    cid = str(uuid.uuid4())
    capabilities = {
        "schema_version": 1,
        "capability_id": capability_id,
        "revision": revision,
        # 默认覆盖批准基线的参数包络（B3：不覆盖的设备行不构成有效确认）
        "parameter_ranges": (
            parameter_ranges
            if parameter_ranges is not None
            else json.loads(json.dumps(DEFAULT_PLAN_CAPABILITY_BASELINE["parameter_ranges"]))
        ),
    }
    obs = observation if observation is not None else {"schema_version": 1, "status": "ok"}
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO microcrystals (id, serial_no, capabilities, latest_observation,"
                " observed_at) VALUES (CAST(:id AS uuid), :sn, CAST(:cap AS jsonb),"
                " CAST(:obs AS jsonb), CASE WHEN :off IS NULL THEN NULL"
                " ELSE CURRENT_TIMESTAMP - make_interval(secs => :off) END)"
            ),
            {
                "id": cid,
                "sn": f"micro-{uuid.uuid4().hex[:8]}",
                "cap": _json(capabilities),
                "obs": _json(obs),
                "off": observed_offset_seconds,
            },
        )
    return cid


def seed_plan(
    engine: Engine,
    *,
    assessment_id: str,
    member_id: str,
    plan_id: Optional[str] = None,
    generation_status: str = "waiting_inputs",
    input_photo_version: Optional[int] = 1,
    generation_revision: int = 0,
    input_snapshot: Optional[dict[str, Any]] = None,
    completed_count: int = 0,
    completed_at: Optional[bool] = False,
    progress_revision: int = 0,
) -> str:
    pid = plan_id or str(uuid.uuid4())
    snapshot = input_snapshot if input_snapshot is not None else {}
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO care_plans (id, assessment_id, member_id, generation_status,"
                " input_photo_version, generation_revision, input_snapshot, completed_count,"
                " completed_at, progress_revision)"
                " VALUES (CAST(:id AS uuid), CAST(:a AS uuid), CAST(:m AS uuid), :gs, :ipv,"
                " :grev, CAST(:snap AS jsonb), :cc,"
                " CASE WHEN :cat THEN CURRENT_TIMESTAMP ELSE NULL END, :pr)"
            ),
            {
                "id": pid,
                "a": assessment_id,
                "m": member_id,
                "gs": generation_status,
                "ipv": input_photo_version,
                "grev": int(generation_revision),
                "snap": _json(snapshot),
                "cc": int(completed_count),
                "cat": bool(completed_at),
                "pr": int(progress_revision),
            },
        )
    return pid


def seed_execution(
    engine: Engine,
    *,
    plan_id: str,
    member_id: str,
    microcrystal_id: str,
    assessment_id: str,
    request_id: str,
    latest_verification: Optional[dict[str, Any]] = None,
    plan_snapshot: Optional[dict[str, Any]] = None,
    closure_manifest: Optional[dict[str, Any]] = None,
) -> str:
    """Seed one open APP-controlled T07 execution (for media reference scans)."""
    eid = str(uuid.uuid4())
    account_id = seed_account(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id,"
                " controller_type, controller_account_id, controller_installation_id,"
                " assessment_id_at_start, latest_verification, plan_snapshot,"
                " closure_manifest, source_request_id)"
                " VALUES (CAST(:id AS uuid), CAST(:plan AS uuid), CAST(:member AS uuid),"
                " CAST(:micro AS uuid), 'app', CAST(:account AS uuid), 'install-test',"
                " CAST(:assessment AS uuid), CAST(:lv AS jsonb), CAST(:ps AS jsonb),"
                " CAST(:cm AS jsonb), CAST(:request AS uuid))"
            ),
            {
                "id": eid,
                "plan": plan_id,
                "member": member_id,
                "micro": microcrystal_id,
                "account": account_id,
                "assessment": assessment_id,
                "lv": _json(latest_verification or {}),
                "ps": _json(plan_snapshot or {}),
                "cm": None if closure_manifest is None else _json(closure_manifest),
                "request": request_id,
            },
        )
    return eid


def seed_media(
    engine: Engine,
    storage: Any,
    *,
    media_id: Optional[str] = None,
    state: str = "available",
    purpose: str = "assessment_result",
    assessment_id: Optional[str] = None,
    execution_id: Optional[str] = None,
    member_id: Optional[str] = None,
    request_id: Optional[str] = None,
    object_key: Optional[str] = None,
    bucket: str = "mvp-media",
    put_object: bool = True,
    environment: str = "dev",
) -> tuple[str, str]:
    """Seed one T11 row (+ storage object). Returns ``(media_id, object_key)``."""
    mid = media_id or str(uuid.uuid4())
    key = object_key or build_object_key(environment, purpose, mid)
    if put_object:
        storage.put(key, PNG_BYTES)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO media_objects (id, bucket, object_key, purpose, assessment_id,"
                " execution_id, member_id, request_id, uploader_type, state, content_type,"
                " byte_size, content_hash)"
                " VALUES (CAST(:id AS uuid), :bucket, :key, :purpose, CAST(:a AS uuid),"
                " CAST(:e AS uuid), CAST(:m AS uuid), CAST(:r AS uuid), 'worker', :state,"
                " 'image/png', :bs, :h)"
            ),
            {
                "id": mid,
                "bucket": bucket,
                "key": key,
                "purpose": purpose,
                "a": assessment_id,
                "e": execution_id,
                "m": member_id,
                "r": request_id,
                "state": state,
                "bs": len(PNG_BYTES),
                "h": "0" * 64,
            },
        )
    return mid, key


def mark_report_ready(
    engine: Engine,
    assessment_id: str,
    *,
    member_id: str,
    report_id: Optional[str] = None,
    report_photo_version: int = 1,
    conclusion: str = "balanced",
) -> str:
    rid = report_id or str(uuid.uuid4())
    payload = {
        "schema_version": 1,
        "conclusion": conclusion,
        "metrics": [{"name": "moisture", "value": 55.0, "unit": "percent"}],
        "description": "seed report",
        "images": [],
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET status='report_ready', member_id=CAST(:m AS uuid),"
                " report_id=CAST(:r AS uuid), report_payload=CAST(:p AS jsonb),"
                " report_summary=CAST(:s AS jsonb), report_photo_version=:rpv,"
                " report_ready_at=CURRENT_TIMESTAMP WHERE id=CAST(:a AS uuid)"
            ),
            {
                "a": assessment_id,
                "m": member_id,
                "r": rid,
                "p": _json(payload),
                "s": _json({"schema_version": 1, "conclusion": conclusion}),
                "rpv": int(report_photo_version),
            },
        )
    return rid


# ---------------------------------------------------------------- job/context


def make_job(
    *,
    job_type: str,
    payload: dict[str, Any],
    owner_type: str,
    owner_id: str,
    input_revision: int = 0,
    dedup_key: Optional[str] = None,
    attempt_count: int = 1,
    max_attempts: int = 5,
) -> JobRow:
    return JobRow(
        id=str(uuid.uuid4()),
        job_type=job_type,
        owner_type=owner_type,
        owner_id=owner_id,
        input_revision=int(input_revision),
        dedup_key=dedup_key or f"test:{uuid.uuid4()}",
        payload=payload,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        lease_revision=1,
        lease_owner="w-d",
    )


def make_ctx(engine: Engine, job: JobRow, *, extras: Optional[dict[str, Any]] = None) -> HandlerContext:
    return HandlerContext(
        engine=engine,
        config=WorkerConfig(runtime_dsn="unused"),
        job=job,
        abort_event=threading.Event(),
        extras=extras or {},
    )


def run_claimed(
    engine: Engine,
    handler: Any,
    job_id: str,
    *,
    extras: Optional[dict[str, Any]] = None,
) -> tuple[str, Optional[JobFailed], JobRow]:
    """领取指定任务 → validate → handle → 代次受控完成/失败/defer 写回。

    返回 ``("succeeded"|"failed"|"deferred", exc_or_None, claim)``。
    ``deferred`` 镜像 loop.py 的 defer 分支（HandlerResult.defer_seconds 非空）。
    """
    claims = claim_batch(engine, worker_id="w-d", lease_seconds=60, batch_size=50)
    claim = next((c for c in claims if c.id == job_id), None)
    assert claim is not None, f"job {job_id} not claimable"
    # 归还本次批量误领的其它任务，保持逐测试单任务语义
    for other in claims:
        if other.id != job_id:
            release_claim(engine, other, worker_id="w-d")
    handler.validate(claim.payload)
    ctx = make_ctx(engine, claim, extras=extras)
    try:
        result = handler.handle(ctx, claim)
    except JobFailed as exc:
        complete_failure(
            engine, claim, code=exc.code, message=exc.message, retryable=exc.retryable,
            backoff_base_seconds=0, backoff_cap_seconds=0,
        )
        return "failed", exc, claim
    if result is not None and result.defer_seconds is not None:
        complete_deferred(
            engine, claim,
            defer_seconds=float(result.defer_seconds),
            business_tx=result.business_tx,
        )
        return "deferred", None, claim
    complete_success(
        engine, claim,
        handler_result_tx=result.business_tx if result is not None else None,
    )
    return "succeeded", None, claim


# ---------------------------------------------------------------- fetch helpers


def fetch_assessment(engine: Engine, assessment_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, status, member_id, current_photo_version, processing_revision,"
                " photo_versions, identity_result, report_id, report_summary, report_payload,"
                " report_photo_version, report_ready_at, failure_code, failure_detail"
                " FROM skin_assessments WHERE id = CAST(:id AS uuid)"
            ),
            {"id": assessment_id},
        ).mappings().first()
    assert row is not None
    return dict(row)


def fetch_plan(engine: Engine, plan_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, assessment_id, member_id, generation_status, input_photo_version,"
                " generation_revision, input_snapshot, plan_summary, plan_payload, target_count,"
                " completed_count, completed_at, progress_revision, failure_detail"
                " FROM care_plans WHERE id = CAST(:id AS uuid)"
            ),
            {"id": plan_id},
        ).mappings().first()
    assert row is not None
    return dict(row)


def count_members(engine: Engine, *, ns: str = DEFAULT_NS, ref: Optional[str] = None) -> int:
    sql = "SELECT count(*) FROM members WHERE identity_namespace = :ns"
    params: dict[str, Any] = {"ns": ns}
    if ref is not None:
        sql += " AND face_subject_ref = :ref"
        params["ref"] = ref
    with engine.connect() as conn:
        return int(conn.execute(text(sql), params).scalar_one())


def fetch_members(engine: Engine, *, ns: str = DEFAULT_NS) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, identity_namespace, face_subject_ref, identity_summary,"
                " created_from_assessment_id, status FROM members WHERE identity_namespace = :ns"
            ),
            {"ns": ns},
        ).mappings().all()
    return [dict(r) for r in rows]


def count_grants(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM member_access_grants")).scalar_one())


def fetch_result_media(
    engine: Engine, assessment_id: str, photo_version: int
) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, state, content_type, byte_size, content_hash, storage_metadata"
                " FROM media_objects WHERE assessment_id = CAST(:a AS uuid)"
                " AND photo_version = :pv AND purpose = 'assessment_result'"
            ),
            {"a": assessment_id, "pv": int(photo_version)},
        ).mappings().all()
    return [dict(r) for r in rows]


def count_jobs_by_dedup(engine: Engine, dedup_key: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM async_jobs WHERE dedup_key = :k"),
                {"k": dedup_key},
            ).scalar_one()
        )


def fetch_job_full_by_dedup(engine: Engine, dedup_key: str) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, job_type, status, owner_type, owner_id, input_revision,"
                " payload, attempt_count, max_attempts, available_at, last_error"
                " FROM async_jobs WHERE dedup_key = :k"
            ),
            {"k": dedup_key},
        ).mappings().first()
    assert row is not None
    return dict(row)


def fetch_job_full_by_id(engine: Engine, job_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, job_type, status, owner_type, owner_id, input_revision,"
                " payload, attempt_count, max_attempts, available_at, last_error"
                " FROM async_jobs WHERE id = CAST(:id AS uuid)"
            ),
            {"id": job_id},
        ).mappings().first()
    assert row is not None
    return dict(row)


def derived_candidate(ns: str, assessment_id: str) -> str:
    return candidate_entity_id(ns, assessment_id)


def derived_namespace_owner(ns: str) -> str:
    return namespace_owner_id(ns)


def enroll_payload(
    *,
    assessment_id: str,
    processing_revision: int,
    photo_version: int,
    images: dict[str, str],
    correlation_id: str,
    provider_config_revision: str = "1",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "correlation_id": correlation_id,
        "assessment_id": assessment_id,
        "photo_version": str(photo_version),
        "processing_revision": str(processing_revision),
        "images": {
            "front": images["front"],
            "left": images["left"],
            "right": images["right"],
        },
        "provider_config_revision": provider_config_revision,
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
