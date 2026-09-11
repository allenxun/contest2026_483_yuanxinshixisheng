"""结果图归档：算法输出图 → 受控 T11 ``assessment_result`` 行 + 存储对象。

流程（DD 9.4 / 10.1）：先按 ``assessment_id + photo_version + purpose`` 单表读取
既有结果图，用 ``storage_metadata->>'provider_ref'`` 匹配复用（至少一次重跑不产生
孤儿重复）；否则插 pending 行 → 存储 put（事务外）→ 置 available（内容类型/大小/
摘要）。任何归档失败都**不发布报告**，由 handler 决定可重试或终止。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from sqlalchemy import Connection, Engine, text

from ...media.storage import build_object_key
from .constants import ALLOWED_RESULT_CONTENT_TYPES, DEFAULT_BUCKET

_SELECT_RESULT_MEDIA = text(
    """
SELECT id, object_key, state, content_type, byte_size, storage_metadata
FROM media_objects
WHERE assessment_id = CAST(:assessment_id AS uuid)
  AND photo_version = :photo_version
  AND purpose = 'assessment_result'
"""
)

# B3：同 (task, photo_version) 的结果图归档串行化（事务级 advisory lock）。
# V1/V2 无结果图唯一约束且迁移禁改，故用 advisory lock 保证并发归档同一
# (task,version,provider_ref) 至多一行 T11、至多一个存储对象。
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
                           member_id, uploader_type, state, storage_metadata,
                           created_at, updated_at)
VALUES (CAST(:id AS uuid), :bucket, :object_key, 'assessment_result',
        CAST(:assessment_id AS uuid), :photo_version, NULL, 'worker', 'pending',
        CAST(:storage_metadata AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
"""
)

_UPDATE_MEDIA_AVAILABLE = text(
    """
UPDATE media_objects
SET state = 'available', content_type = :content_type, byte_size = :byte_size,
    content_hash = :content_hash, storage_metadata = CAST(:storage_metadata AS jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND state IN ('pending', 'available')
"""
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


def archive_result_images(
    engine: Engine,
    storage: Any,
    *,
    environment: str,
    assessment_id: str,
    photo_version: int,
    result_images: list[dict[str, Any]],
    max_bytes: int,
) -> list[dict[str, Any]]:
    """归档结果图；返回 ``[{"media_id","caption","content_type"}]``（保序）。

    B3：整段 (assessment_id, photo_version) 归档在**单个事务**内持
    ``pg_advisory_xact_lock``：先加锁再重读既有行，使并发同 ref 归档串行——后到者
    锁后读到先到者已 available 的行 → 直接复用（不插入、不写存储）。存储 put 与
    T11 行插入/更新同在该锁内，故恰好一行一对象，双方拿到同一 media_id。
    put 失败 → 整个归档事务回滚（不留 pending 半写），由 handler 决定重试/终止。
    """
    with engine.begin() as conn:
        conn.execute(
            _ADVISORY_LOCK,
            {"assessment_id": assessment_id, "photo_version": int(photo_version)},
        )
        by_ref = _load_by_ref_conn(conn, assessment_id, photo_version)
        archived: list[dict[str, Any]] = []

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

            existing = by_ref.get(ref)
            if (
                existing is not None
                and existing.get("state") == "available"
                and existing.get("content_type") == content_type
                and existing.get("byte_size") == len(data)
            ):
                archived.append(
                    {"media_id": str(existing["id"]), "caption": caption, "content_type": content_type}
                )
                continue

            if existing is None:
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
                        "storage_metadata": _json(meta),
                    },
                )
                row = {
                    "id": media_id,
                    "object_key": object_key,
                    "state": "pending",
                    "content_type": None,
                    "byte_size": None,
                    "storage_metadata": meta,
                }
                by_ref[ref] = row
                existing = row
            else:
                media_id = str(existing["id"])
                object_key = str(existing["object_key"])

            try:
                storage.put(object_key, data)  # 与行写入同持 advisory lock
            except Exception as exc:
                raise ArchiveError(
                    "RESULT_ARCHIVE_FAILED", "storage put failed", terminal=False
                ) from exc

            meta = {"schema_version": 1, "provider_ref": ref}
            digest = hashlib.sha256(data).hexdigest()
            conn.execute(
                _UPDATE_MEDIA_AVAILABLE,
                {
                    "id": media_id,
                    "content_type": content_type,
                    "byte_size": len(data),
                    "content_hash": digest,
                    "storage_metadata": _json(meta),
                },
            )
            existing.update({"state": "available", "content_type": content_type, "byte_size": len(data)})
            archived.append({"media_id": media_id, "caption": caption, "content_type": content_type})

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
