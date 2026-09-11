"""``identity.enroll``：namespace 级新人登记协调（DD §9.3）。

输入被补拍替换时不得把旧登记结果归给新照片（先做 processing_revision +
photo_version 双向复核）；外部成功但业务取消的人员资源保留受控对账（成员可
无关联，记日志），绝不在未确认可见时释放阻塞去登记第二份同人候选。
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Connection, Engine, text

from ..logging_setup import mlog
from ..runtime.complete import StaleGeneration
from ..runtime.rows import JobRow
from . import HandlerContext, HandlerResult, JobFailed
from .dshared.constants import (
    candidate_entity_id,
    provider_request_id,
)
from .dshared.dfence import fenced_business_tx
from .dshared.dmedia import load_image_bytes
from .dshared.jsonschema_support import load_payload_validator, validate_payload
from .dshared.providers import ProviderUnavailable
from .dshared.resolve import dconfig_for, face_port_for, storage_for

log = logging.getLogger("mvp_worker.handlers.identity_enroll")

JOB_TYPE = "identity.enroll"
_PAYLOAD_SCHEMA = "payload-identity-enroll.json"

_SELECT_ASSESSMENT_FOR_UPDATE = text(
    """
SELECT id, status, current_photo_version, processing_revision
FROM skin_assessments
WHERE id = CAST(:id AS uuid)
FOR UPDATE
"""
)

_PERSIST_ENROLL_STARTED = text(
    """
UPDATE skin_assessments
SET identity_result = CAST(:identity_result AS jsonb), updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND processing_revision = :rev
  AND status IN ('queued', 'analyzing')
"""
)

_INSERT_MEMBER = text(
    """
INSERT INTO members (id, identity_namespace, face_subject_ref, profile,
                     identity_summary, created_from_assessment_id, status,
                     created_at, updated_at)
VALUES (CAST(:id AS uuid), :ns, :ref, '{}'::jsonb,
        CAST(:identity_summary AS jsonb), CAST(:assessment_id AS uuid), 'active',
        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (identity_namespace, face_subject_ref)
    WHERE identity_namespace IS NOT NULL AND face_subject_ref IS NOT NULL
DO NOTHING
RETURNING id
"""
)

_SELECT_MEMBER_ID = text(
    "SELECT id FROM members WHERE identity_namespace = :ns AND face_subject_ref = :ref"
)

_LINK_MEMBER = text(
    """
UPDATE skin_assessments
SET member_id = CAST(:member_id AS uuid),
    identity_result = CAST(:identity_result AS jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND processing_revision = :rev
  AND current_photo_version = :photo_version
  -- B2：仅在仍处本候选登记窗口时归属。并发的 analyze 重试若已写 needs_retake
  -- （status 不再是 analyzing）或换成本候选以外的输入，这里 0 行 → 不归属、不覆盖
  -- identity_result；成员行保留（外部登记真实发生，受控对账），任务仍成功。
  AND status = 'analyzing'
  AND identity_result ->> 'candidate_entity_id' = :candidate_entity_id
  AND identity_result ->> 'phase' IN ('enroll_pending', 'enroll_started')
"""
)


class IdentityEnrollHandler:
    name = "identity-enroll"

    def __init__(self) -> None:
        self._validator = None
        self._lock = threading.Lock()

    def _get_validator(self):
        if self._validator is None:
            with self._lock:
                if self._validator is None:
                    self._validator = load_payload_validator(_PAYLOAD_SCHEMA)
        return self._validator

    def validate(self, payload: object) -> None:
        validate_payload(self._get_validator(), payload, _PAYLOAD_SCHEMA)

    def handle(self, ctx: HandlerContext, job: JobRow) -> Optional[HandlerResult]:
        """围栏包装：standalone 阶段持久化在租约失效时返回 None（见 dshared/dfence）。"""
        try:
            return self._handle(ctx, job)
        except StaleGeneration:
            mlog(
                log, logging.DEBUG, "enroll.fenced_write_stale",
                **job.log_fields(), note="lease lost; phase persist rolled back",
            )
            return None

    def _handle(self, ctx: HandlerContext, job: JobRow) -> Optional[HandlerResult]:
        assessment_id = str(job.payload["assessment_id"])
        rev = int(job.payload["processing_revision"])
        photo_version = int(job.payload["photo_version"])
        correlation_id = str(job.payload["correlation_id"])
        dcfg = dconfig_for(ctx)
        ns = dcfg.identity_namespace

        row = _load_assessment(ctx.engine, assessment_id)
        if row is None:
            raise JobFailed("ASSESSMENT_NOT_FOUND", "assessment row missing", retryable=False)

        # 输入已被补拍替换 → 不调用供应商、不归属旧结果（DD 9.3）
        if (
            int(row["processing_revision"]) != rev
            or int(row["current_photo_version"]) != photo_version
        ):
            mlog(log, logging.INFO, "enroll.stale_input", **job.log_fields())
            return None

        media_ids = {
            "front": str(job.payload["images"]["front"]),
            "left": str(job.payload["images"]["left"]),
            "right": str(job.payload["images"]["right"]),
        }
        images = load_image_bytes(ctx.engine, storage_for(ctx), media_ids)
        if isinstance(images, str):
            self._transient_or_terminal(
                ctx, job, code="SOURCE_IMAGE_UNAVAILABLE",
                message="enrollment source image unavailable", reason=images,
            )
            return None  # pragma: no cover

        candidate_id = candidate_entity_id(ns, assessment_id)
        request_id = provider_request_id(correlation_id)

        # 2) 外部调用前先持久记录阶段（可恢复/可对账）
        started = {
            "schema_version": 1,
            "classification": "reliable_new",
            "candidate_entity_id": candidate_id,
            "phase": "enroll_started",
            "correlation_id": correlation_id,
            "provider_request_id": request_id,
        }
        if not _persist_started(ctx.engine, job, assessment_id, rev, started):
            mlog(log, logging.INFO, "enroll.persist_started_noop", **job.log_fields())
            return None

        face = face_port_for(ctx)
        if ctx.abort_event.is_set():
            return None

        # 3) 外部登记（锁外）；超时/未知 → 同 EntityId 对账，绝不生成另一 ID 盲重试
        try:
            registered = face.register_person(
                ns, candidate_id, images, correlation_id, request_id
            )
        except ProviderUnavailable:
            return self._reconcile(
                ctx, job, face, ns, candidate_id, correlation_id, request_id
            )

        status = getattr(registered, "status", "failed")
        if status in ("success", "timeout", "unknown"):
            visible = face.query_registration(
                correlation_id, request_id, namespace=ns, entity_id=candidate_id
            )
            if getattr(visible, "status", None) != "registered":
                self._transient_or_terminal(
                    ctx, job, code="ENROLLMENT_RECONCILE_PENDING",
                    message="registration not confirmed visible",
                    reason="provider visibility not confirmed",
                )
                return None  # pragma: no cover
        else:
            self._transient_or_terminal(
                ctx, job, code="ENROLLMENT_FAILED",
                message="face registration failed", reason="provider register failed",
            )
            return None  # pragma: no cover

        identity_summary = _identity_summary(
            correlation_id=correlation_id,
            request_id=request_id,
            provider_config_revision=dcfg.provider_config_revision,
            assessment_id=assessment_id,
            photo_version=photo_version,
            media_ids=media_ids,
        )
        return HandlerResult(
            business_tx=lambda conn: _commit_enrollment(
                conn,
                assessment_id=assessment_id,
                rev=rev,
                photo_version=photo_version,
                namespace=ns,
                candidate_id=candidate_id,
                correlation_id=correlation_id,
                identity_summary=identity_summary,
            )
        )

    # ------------------------------------------------------------- helpers

    def _reconcile(
        self,
        ctx: HandlerContext,
        job: JobRow,
        face: Any,
        ns: str,
        candidate_id: str,
        correlation_id: str,
        request_id: str,
    ) -> Optional[HandlerResult]:
        try:
            visible = face.query_registration(
                correlation_id, request_id, namespace=ns, entity_id=candidate_id
            )
        except ProviderUnavailable:
            self._transient_or_terminal(
                ctx, job, code="ENROLLMENT_RECONCILE_PENDING",
                message="registration reconciliation unavailable",
                reason="query_registration unavailable",
            )
            return None  # pragma: no cover
        if getattr(visible, "status", None) != "registered":
            self._transient_or_terminal(
                ctx, job, code="ENROLLMENT_RECONCILE_PENDING",
                message="registration outcome unknown; reconcile pending",
                reason="provider registration not confirmed",
            )
            return None  # pragma: no cover
        # 对账确认已登记 → 走正常归属（不重新调用 register_person）
        dcfg = dconfig_for(ctx)
        media_ids = {
            "front": str(job.payload["images"]["front"]),
            "left": str(job.payload["images"]["left"]),
            "right": str(job.payload["images"]["right"]),
        }
        identity_summary = _identity_summary(
            correlation_id=correlation_id,
            request_id=request_id,
            provider_config_revision=dcfg.provider_config_revision,
            assessment_id=str(job.payload["assessment_id"]),
            photo_version=int(job.payload["photo_version"]),
            media_ids=media_ids,
        )
        return HandlerResult(
            business_tx=lambda conn: _commit_enrollment(
                conn,
                assessment_id=str(job.payload["assessment_id"]),
                rev=int(job.payload["processing_revision"]),
                photo_version=int(job.payload["photo_version"]),
                namespace=ns,
                candidate_id=candidate_id,
                correlation_id=correlation_id,
                identity_summary=identity_summary,
            )
        )

    def _transient_or_terminal(
        self,
        ctx: HandlerContext,
        job: JobRow,
        *,
        code: str,
        message: str,
        reason: str,
    ) -> None:
        if job.attempt_count >= job.max_attempts:
            # 槽位保持占用：job 落 failed，uq_job_identity_enroll（含 failed）继续阻塞
            # 同 namespace 的其它候选；需运维对账后人工置 cancelled/succeeded 才释放。
            mlog(
                log, logging.ERROR, "enroll.terminal_occupied_slot",
                **job.log_fields(), code=code, reason=reason[:200],
            )
            raise JobFailed(code, message, retryable=False)
        raise JobFailed(code, message, retryable=True)


# ---------------------------------------------------------------- module helpers


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_assessment(engine: Engine, assessment_id: str) -> Optional[dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, current_photo_version, processing_revision"
                " FROM skin_assessments WHERE id = CAST(:id AS uuid)"
            ),
            {"id": assessment_id},
        ).mappings().first()
    return dict(row) if row is not None else None


def _persist_started(
    engine: Engine, job: JobRow, assessment_id: str, rev: int, identity_result: dict[str, Any]
) -> bool:
    with fenced_business_tx(engine, job) as conn:
        res = conn.execute(
            _PERSIST_ENROLL_STARTED,
            {"id": assessment_id, "rev": rev, "identity_result": _json(identity_result)},
        )
        return res.rowcount > 0


def _identity_summary(
    *,
    correlation_id: str,
    request_id: str,
    provider_config_revision: str,
    assessment_id: str,
    photo_version: int,
    media_ids: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "enrollment": {
            "correlation_id": correlation_id,
            "provider_request_id": request_id,
            "provider_config_revision": provider_config_revision,
            "registered_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "source_assessment_id": assessment_id,
            "photo_version": photo_version,
        },
        "reference_media": {
            "front": media_ids["front"],
            "left": media_ids["left"],
            "right": media_ids["right"],
        },
    }


def _commit_enrollment(
    conn: Connection,
    *,
    assessment_id: str,
    rev: int,
    photo_version: int,
    namespace: str,
    candidate_id: str,
    correlation_id: str,
    identity_summary: dict[str, Any],
) -> None:
    # 锁顺序：先 T05（业务行），再 T01（members），最后运行时 T12。
    locked = conn.execute(
        _SELECT_ASSESSMENT_FOR_UPDATE, {"id": assessment_id}
    ).mappings().first()
    fresh = (
        locked is not None
        and int(locked["processing_revision"]) == rev
        and int(locked["current_photo_version"]) == photo_version
    )

    member_id = str(uuid.uuid4())
    inserted = conn.execute(
        _INSERT_MEMBER,
        {
            "id": member_id,
            "ns": namespace,
            "ref": candidate_id,
            "identity_summary": _json(identity_summary),
            "assessment_id": assessment_id,
        },
    ).first()
    if inserted is None:
        existing = conn.execute(
            _SELECT_MEMBER_ID, {"ns": namespace, "ref": candidate_id}
        ).first()
        if existing is not None:
            member_id = str(existing[0])

    if not fresh:
        # 外部已成功但输入被替换：成员保留（受控对账），不归给新照片。
        mlog(
            log, logging.INFO, "enroll.member_retained_stale_input",
            assessmentId=assessment_id, memberId=member_id,
        )
        return

    identity_result = {
        "schema_version": 1,
        "classification": "reliable_new",
        "candidate_entity_id": candidate_id,
        "phase": "enrolled",
        "correlation_id": correlation_id,
        "member_id": member_id,
    }
    res = conn.execute(
        _LINK_MEMBER,
        {
            "id": assessment_id,
            "rev": rev,
            "photo_version": photo_version,
            "candidate_entity_id": candidate_id,
            "member_id": member_id,
            "identity_result": _json(identity_result),
        },
    )
    if res.rowcount == 0:
        # B2：并发 analyze 重试已把 T05 带离本候选登记窗口（如 needs_retake）。
        # 不归属、不覆盖 identity_result；外部登记真实存在，成员行保留待对账。
        mlog(
            log, logging.WARNING, "enroll.link_guard_rejected",
            assessmentId=assessment_id, candidateEntityId=candidate_id,
            memberId=member_id,
            note="assessment left enrollment window; member retained unlinked",
        )


handler = IdentityEnrollHandler()
