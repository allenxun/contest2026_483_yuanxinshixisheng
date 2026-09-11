"""``media.cleanup``：仅清理明确无引用的失败/未被接纳上传（DD 10.3，裁定 5）。

只做状态迁移 + 存储对象删除，**永不 DELETE T11 行**；不使用任何 TTL；绝不清理
已归属/被业务引用的对象。锁顺序（DD 10.3）：先做 T13 处理者活性与业务引用核查
（单表只读、不过早持 T11 行锁），后进入两段式 ``deleting →（锁外存储删除，幂等）
→ deleted``；崩溃/重跑可从 ``deleting`` 恢复。本 handler 不写任何其它表。
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from sqlalchemy import Connection, Engine, text

from ..logging_setup import mlog
from ..runtime.rows import JobRow
from . import HandlerContext, HandlerResult, JobFailed
from .dshared.denqueue import enqueue_job
from .dshared.jsonschema_support import load_payload_validator, validate_payload
from .dshared.resolve import storage_for

log = logging.getLogger("mvp_worker.handlers.media_cleanup")

JOB_TYPE = "media.cleanup"
_PAYLOAD_SCHEMA = "payload-media-cleanup.json"

_SELECT_MEDIA = text(
    """
SELECT id, bucket, object_key, purpose, state, assessment_id, execution_id,
       member_id, request_id
FROM media_objects
WHERE id = CAST(:id AS uuid)
"""
)

# T13 处理者活性（单表只读；先于任何 T11 锁）
_SELECT_PROCESSOR_ACTIVE = text(
    """
SELECT (status = 'processing' AND lease_until IS NOT NULL
        AND lease_until > CURRENT_TIMESTAMP)
FROM idempotency_requests
WHERE id = CAST(:id AS uuid)
"""
)

# 业务引用文本包含扫描（单表 EXISTS，MVP 规模可接受，无 JOIN）
_REF_SKIN_ASSESSMENTS = text(
    """
SELECT EXISTS (
  SELECT 1 FROM skin_assessments
  WHERE CAST(photo_versions AS text) LIKE '%' || :media_id || '%'
     OR CAST(report_payload AS text) LIKE '%' || :media_id || '%'
)
"""
)

_REF_MEMBERS = text(
    """
SELECT EXISTS (
  SELECT 1 FROM members
  WHERE CAST(identity_summary AS text) LIKE '%' || :media_id || '%'
)
"""
)

_REF_CARE_EXECUTIONS = text(
    """
SELECT EXISTS (
  SELECT 1 FROM care_executions
  WHERE CAST(latest_verification AS text) LIKE '%' || :media_id || '%'
     OR CAST(plan_snapshot AS text) LIKE '%' || :media_id || '%'
     OR CAST(closure_manifest AS text) LIKE '%' || :media_id || '%'
)
"""
)

_REF_IDEMPOTENCY = text(
    """
SELECT EXISTS (
  SELECT 1 FROM idempotency_requests
  WHERE CAST(verification_summary AS text) LIKE '%' || :media_id || '%'
     OR CAST(result_summary AS text) LIKE '%' || :media_id || '%'
)
"""
)

# tx-A：原子占位 deleting（仅无归属可清理行）
_MARK_DELETING = text(
    """
UPDATE media_objects
SET state = 'deleting', updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid)
  AND state IN ('pending', 'available', 'failed')
  AND assessment_id IS NULL AND execution_id IS NULL AND member_id IS NULL
"""
)

# tx-B：确认已删除（不触碰 storage_metadata）
_MARK_DELETED = text(
    """
UPDATE media_objects
SET state = 'deleted', updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND state = 'deleting'
"""
)

# 有界候选扫描：无归属可清理的孤儿（单表；不含 TTL，无 JOIN）
_SELECT_ORPHAN_CANDIDATES = text(
    """
SELECT id, bucket, object_key, purpose, state, request_id,
       assessment_id, execution_id, member_id
FROM media_objects
WHERE state IN ('pending', 'available', 'failed')
  AND assessment_id IS NULL AND execution_id IS NULL AND member_id IS NULL
ORDER BY created_at, id
LIMIT :limit
"""
)

# 发现入队使用的确定性修订（无业务代次时固定 1，保证 dedup 幂等）
_DISCOVERY_REVISION = 1


class MediaCleanupHandler:
    name = "media-cleanup"

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
        media_id = str(job.payload["media_object_id"])

        row = _load_media(ctx.engine, media_id)
        if row is None:
            return None  # 行不存在：已无对象可清，no-op 成功
        state = row["state"]
        if state == "deleted":
            return None  # 已删除：幂等 no-op 成功

        if state != "deleting":
            # 2) 范围守卫：只清失败行或未被接纳的无归属上传
            if not _cleanable(row):
                mlog(
                    log, logging.ERROR, "media.cleanup.referenced_or_owned",
                    **job.log_fields(), mediaId=media_id, media_state=state,
                )
                raise JobFailed(
                    "MEDIA_REFERENCED", "media object is owned or accepted", retryable=False
                )
            # 3) 处理者活性 + 业务引用核查（先于任何 T11 锁）
            request_id = row["request_id"]
            if request_id is not None and _processor_active(ctx.engine, str(request_id)):
                raise JobFailed(
                    "PROCESSOR_ACTIVE", "ingest processor lease still active", retryable=True
                )
            if _referenced(ctx.engine, media_id):
                mlog(
                    log, logging.ERROR, "media.cleanup.referenced",
                    **job.log_fields(), mediaId=media_id,
                )
                raise JobFailed(
                    "MEDIA_REFERENCED", "media object is referenced by business data",
                    retryable=False,
                )
            # 4) tx-A：原子进入 deleting（0 行 → 重读判定）
            if not _mark_deleting(ctx.engine, media_id):
                again = _load_media(ctx.engine, media_id)
                if again is None or again["state"] == "deleted":
                    return None
                if not _ownership_null(again):
                    mlog(
                        log, logging.ERROR, "media.cleanup.referenced_after_guard",
                        **job.log_fields(), mediaId=media_id,
                    )
                    raise JobFailed(
                        "MEDIA_REFERENCED", "media object became owned/referenced",
                        retryable=False,
                    )
                raise JobFailed(
                    "CLEANUP_CONTENDED", "media cleanup concurrently progressing",
                    retryable=True,
                )

        # 4) 锁外存储删除（幂等：对象不存在视为已删除）
        if ctx.abort_event.is_set():
            return None
        _delete_object(storage_for(ctx), str(row["object_key"]))

        # tx-B：确认 deleted（0 行 → 并发操作，no-op）
        return HandlerResult(
            business_tx=lambda conn: _mark_deleted(conn, media_id)
        )


# ---------------------------------------------------------------- module helpers


def _load_media(engine: Engine, media_id: str) -> Optional[dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(_SELECT_MEDIA, {"id": media_id}).mappings().first()
    return dict(row) if row is not None else None


def _cleanable(row: dict[str, Any]) -> bool:
    state = row["state"]
    if state == "failed":
        return True
    if state in ("pending", "available"):
        return _ownership_null(row)
    return False


def _ownership_null(row: dict[str, Any]) -> bool:
    return (
        row["assessment_id"] is None
        and row["execution_id"] is None
        and row["member_id"] is None
    )


def _processor_active(engine: Engine, request_id: str) -> bool:
    with engine.connect() as conn:
        value = conn.execute(
            _SELECT_PROCESSOR_ACTIVE, {"id": request_id}
        ).scalar_one_or_none()
    return bool(value)


def _referenced(engine: Engine, media_id: str) -> bool:
    with engine.connect() as conn:
        for stmt in (
            _REF_SKIN_ASSESSMENTS,
            _REF_MEMBERS,
            _REF_CARE_EXECUTIONS,
            _REF_IDEMPOTENCY,
        ):
            if bool(conn.execute(stmt, {"media_id": media_id}).scalar_one()):
                return True
    return False


def _mark_deleting(engine: Engine, media_id: str) -> bool:
    with engine.begin() as conn:
        res = conn.execute(_MARK_DELETING, {"id": media_id})
    return res.rowcount > 0


def _mark_deleted(conn: Connection, media_id: str) -> None:
    conn.execute(_MARK_DELETED, {"id": media_id})


def _delete_object(storage: Any, object_key: str) -> None:
    """锁外删除对象；对象不存在视为已删除，其它错误可重试（行保持 deleting）。"""
    try:
        storage.delete(object_key)
        return
    except Exception:
        try:
            if not storage.exists(object_key):
                return  # 对象已不存在：幂等恢复
        except Exception:
            pass
        raise JobFailed(
            "STORAGE_DELETE_FAILED", "object storage delete failed", retryable=True
        )


def discover_and_enqueue_orphans(engine: Engine, *, limit: int = 100) -> int:
    """有界扫描无归属孤儿并**幂等**入队 ``media.cleanup``；返回新入队任务数。

    覆盖 crash-after-ingest 形态（T13 succeeded/rejected/过期 processing + 未被
    受理的 T11 行 + 已落存储对象）。复用 handler 的安全证明：处理者活跃租约、
    任一业务引用包含命中 → 不删也不入队。dedup ``media:{id}:cleanup:1`` 保证
    重复发现不产生新任务。无新表、无 TTL、不周期接入（周期接入归总协调）。
    """
    enqueued = 0
    with engine.connect() as conn:
        rows = conn.execute(
            _SELECT_ORPHAN_CANDIDATES, {"limit": int(limit)}
        ).mappings().all()
    for row in rows:
        media_id = str(row["id"])
        candidate = dict(row)
        if not _cleanable(candidate):
            continue
        request_id = candidate["request_id"]
        if request_id is not None and _processor_active(engine, str(request_id)):
            continue  # 处理者租约仍活跃：安全证明不足，跳过
        if _referenced(engine, media_id):
            continue  # 任一业务引用包含命中：不删不入队
        _, replayed = enqueue_job(
            engine,
            job_type=JOB_TYPE,
            dedup_key=f"media:{media_id}:cleanup:{_DISCOVERY_REVISION}",
            owner_type="media",
            owner_id=media_id,
            input_revision=_DISCOVERY_REVISION,
            payload={
                "schema_version": 1,
                "media_object_id": media_id,
                "cleanup_revision": str(_DISCOVERY_REVISION),
            },
        )
        if not replayed:
            enqueued += 1
    return enqueued


handler = MediaCleanupHandler()
