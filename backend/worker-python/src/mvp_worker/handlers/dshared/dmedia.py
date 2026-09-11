"""结果图归档：算法输出图 → 受控 T11 ``assessment_result`` 行 + 存储对象。

两阶段协议（DD §8.4 / §9.2；oracle R1-N1）：存储不可随 PG 事务回滚，故
**先持久化意图 → 上传 → 字段级提升**：

1. **tx1**（持事务级 advisory lock ``d:result-archive:<aid>:<pv>``）：按
   ``assessment_id + photo_version + provider_ref`` 读取既有行；有（pending 或
   available）则复用其 media_id/object_key；无则生成一次 UUID + object key 并
   INSERT ``pending`` 行（含 content_type/provider_ref）。COMMIT。advisory lock 使
   并发创建同一 ref **恰一行一 key**。
2. **锁外上传**：``storage.put(object_key, data)``，同一 key 每次重试幂等覆盖；
   put 失败保留 pending 行（重试续跑，非回滚）。
3. **tx2**（短事务；D handler 内走 :func:`fenced_business_tx` 租约围栏）：
   ``UPDATE ... state='available' WHERE id=:id AND state='pending'``；rowcount 0 →
   并发已提升 → 复读要求 available 且同 object_key。

保证：绝无「有对象无行」；同一 provider_ref 绝不出现第二行/第二个 key；任一点
崩溃后重试复用 pending 行与同一 key 收敛（不产生旧对象变孤儿）。任何归档失败都
不发布报告，由 handler 决定重试/终止。

残留（披露）：终态失败任务遗留的 owned ``pending`` 行仍受当前孤儿规则限制（不清理）
——但**行存在即可被 T11 扫描发现**，非「无行对象」，可接受。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from sqlalchemy import Connection, Engine, text

from ...media.storage import build_object_key
from ...runtime.rows import JobRow
from .constants import ALLOWED_RESULT_CONTENT_TYPES, DEFAULT_BUCKET
from .dfence import fenced_business_tx

_SELECT_RESULT_MEDIA = text(
    """
SELECT id, object_key, state, content_type, byte_size, storage_metadata
FROM media_objects
WHERE assessment_id = CAST(:assessment_id AS uuid)
  AND photo_version = :photo_version
  AND purpose = 'assessment_result'
"""
)

# N1：同 (task, photo_version) 的结果图归档串行化（事务级 advisory lock）。
# V1/V2 无结果图唯一约束且迁移禁改，故用 advisory lock 保证并发归档同一
# (task,version,provider_ref) 至多一行 T11、至多一个存储对象/object key。
_ADVISORY_LOCK = text(
    """
SELECT pg_advisory_xact_lock(
    hashtextextended(
        'd:result-archive:' || :assessment_id || ':' || CAST(:photo_version AS text), 0
    )
)
"""
)

_INSERT_RESULT_MEDIA = text(
    """
INSERT INTO media_objects (id, bucket, object_key, purpose, assessment_id, photo_version,
                           member_id, uploader_type, state, content_type, storage_metadata,
                           created_at, updated_at)
VALUES (CAST(:id AS uuid), :bucket, :object_key, 'assessment_result',
        CAST(:assessment_id AS uuid), :photo_version, NULL, 'worker', 'pending',
        :content_type, CAST(:storage_metadata AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
"""
)

# tx2：pending → available 的字段级提升（0 行 = 并发已提升）
_PROMOTE_PENDING_MEDIA = text(
    """
UPDATE media_objects
SET state = 'available', content_type = :content_type, byte_size = :byte_size,
    content_hash = :content_hash, storage_metadata = CAST(:storage_metadata AS jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND state = 'pending'
"""
)

_SELECT_MEDIA_BY_ID = text(
    "SELECT id, object_key, state FROM media_objects WHERE id = CAST(:id AS uuid)"
)

_SELECT_SOURCE_MEDIA = text(
    "SELECT id, object_key, state FROM media_objects WHERE id = CAST(:id AS uuid)"
)


class ArchiveError(RuntimeError):
    """结果图归档失败；``terminal`` 表示重试无法恢复。"""

    def __init__(self, code: str, message: str, *, terminal: bool) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.terminal = terminal


def sniff_content_type(data: bytes) -> Optional[str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _load_by_ref_conn(
    conn: Connection, assessment_id: str, photo_version: int
) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        _SELECT_RESULT_MEDIA,
        {"assessment_id": assessment_id, "photo_version": int(photo_version)},
    ).mappings().all()
    by_ref: dict[str, dict[str, Any]] = {}
    for row in rows:
        meta = row["storage_metadata"] or {}
        ref = meta.get("provider_ref") if isinstance(meta, dict) else None
        if isinstance(ref, str) and ref and ref not in by_ref:
            by_ref[ref] = dict(row)
    return by_ref


def _promote_tx(engine: Engine, job: Optional[JobRow]) -> Any:
    """tx2 短事务上下文：D handler 有 ``job`` 时走租约围栏；测试/无 job 时普通事务。"""
    if job is not None:
        return fenced_business_tx(engine, job)
    return engine.begin()


def _ensure_pending_row(
    engine: Engine,
    *,
    environment: str,
    assessment_id: str,
    photo_version: int,
    ref: str,
    content_type: str,
) -> tuple[str, str, dict[str, Any]]:
    """tx1：advisory lock 下复用既有行或创建 pending 行；返回 (media_id, key, row)。"""
    with engine.begin() as conn:
        conn.execute(
            _ADVISORY_LOCK,
            {"assessment_id": assessment_id, "photo_version": int(photo_version)},
        )
        by_ref = _load_by_ref_conn(conn, assessment_id, photo_version)
        existing = by_ref.get(ref)
        if existing is not None:
            return str(existing["id"]), str(existing["object_key"]), dict(existing)
        media_id = str(uuid.uuid4())
        object_key = build_object_key(environment, "assessment_result", media_id)
        meta = {"schema_version": 1, "provider_ref": ref}
        conn.execute(
            _INSERT_RESULT_MEDIA,
            {
                "id": media_id,
                "bucket": DEFAULT_BUCKET,
                "object_key": object_key,
                "assessment_id": assessment_id,
                "photo_version": int(photo_version),
                "content_type": content_type,
                "storage_metadata": _json(meta),
            },
        )
        return media_id, object_key, {
            "id": media_id,
            "object_key": object_key,
            "state": "pending",
            "content_type": content_type,
            "byte_size": None,
        }


def archive_result_images(
    engine: Engine,
    storage: Any,
    *,
    environment: str,
    assessment_id: str,
    photo_version: int,
    result_images: list[dict[str, Any]],
    max_bytes: int,
    job: Optional[JobRow] = None,
) -> list[dict[str, Any]]:
    """归档结果图；返回 ``[{"media_id","caption","content_type"}]``（保序）。

    两阶段见模块 docstring：tx1 建/复用 pending 行（advisory lock），锁外 put
    同一 key，tx2 提升 available。``job`` 非空时 tx2 走租约围栏。
    """
    validated: list[tuple[str, str, bytes, str]] = []
    for image in result_images:
        if not isinstance(image, dict):
            raise ArchiveError("RESULT_ARCHIVE_FAILED", "result image not an object", terminal=True)
        ref = image.get("ref")
        caption = image.get("caption", "")
        data = image.get("bytes")
        if not isinstance(ref, str) or not ref:
            raise ArchiveError("RESULT_ARCHIVE_FAILED", "result image missing ref", terminal=True)
        if not isinstance(caption, str):
            raise ArchiveError("RESULT_ARCHIVE_FAILED", "result image caption not a string", terminal=True)
        if not isinstance(data, (bytes, bytearray)):
            raise ArchiveError(
                "RESULT_ARCHIVE_FAILED", "result image bytes missing", terminal=True
            )
        data = bytes(data)
        if len(data) > int(max_bytes):
            raise ArchiveError("RESULT_ARCHIVE_FAILED", "result image exceeds size cap", terminal=True)
        content_type = sniff_content_type(data)
        if content_type not in ALLOWED_RESULT_CONTENT_TYPES:
            raise ArchiveError(
                "RESULT_ARCHIVE_FAILED", "result image content type not allowed", terminal=True
            )
        validated.append((ref, caption, data, content_type))

    archived: list[dict[str, Any]] = []
    for ref, caption, data, content_type in validated:
        media_id, object_key, row = _ensure_pending_row(
            engine,
            environment=environment,
            assessment_id=assessment_id,
            photo_version=photo_version,
            ref=ref,
            content_type=content_type,
        )
        if (
            row.get("state") == "available"
            and row.get("content_type") == content_type
            and row.get("byte_size") == len(data)
        ):
            archived.append(
                {"media_id": media_id, "caption": caption, "content_type": content_type}
            )
            continue

        # 锁外上传：同一 key 每次重试幂等覆盖；失败保留 pending 行供重试续跑。
        try:
            storage.put(object_key, data)
        except Exception as exc:
            raise ArchiveError(
                "RESULT_ARCHIVE_FAILED", "storage put failed", terminal=False
            ) from exc

        digest = hashlib.sha256(data).hexdigest()
        meta = {"schema_version": 1, "provider_ref": ref}
        with _promote_tx(engine, job) as conn:
            res = conn.execute(
                _PROMOTE_PENDING_MEDIA,
                {
                    "id": media_id,
                    "content_type": content_type,
                    "byte_size": len(data),
                    "content_hash": digest,
                    "storage_metadata": _json(meta),
                },
            )
            if res.rowcount == 0:
                again = conn.execute(
                    _SELECT_MEDIA_BY_ID, {"id": media_id}
                ).mappings().first()
                if (
                    again is None
                    or again["state"] != "available"
                    or str(again["object_key"]) != object_key
                ):
                    raise ArchiveError(
                        "RESULT_ARCHIVE_FAILED",
                        "result media promotion lost concurrently",
                        terminal=False,
                    )
        archived.append(
            {"media_id": media_id, "caption": caption, "content_type": content_type}
        )

    return archived


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def load_image_bytes(
    engine: Engine, storage: Any, media_ids: dict[str, str]
) -> "dict[str, bytes] | str":
    """按 media_id 读取各视角对象字节；失败返回原因字符串（保持单表读、无 JOIN）。"""
    out: dict[str, bytes] = {}
    for view, media_id in media_ids.items():
        with engine.connect() as conn:
            row = conn.execute(_SELECT_SOURCE_MEDIA, {"id": media_id}).mappings().first()
        if row is None:
            return f"media row missing for view {view}"
        if row["state"] != "available":
            return f"media not available for view {view}"
        try:
            out[view] = storage.get(str(row["object_key"]))
        except Exception:  # 存储瞬时不可读 → 可重试
            return f"storage read failed for view {view}"
    return out
