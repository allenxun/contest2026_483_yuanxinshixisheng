"""media_objects 单表读（字段显式列出；禁 SELECT *，禁 JOIN）。"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Engine, text

_SELECT_MEDIA = text(
    """
SELECT id, bucket, object_key, purpose, assessment_id, photo_version,
       execution_id, request_id, member_id, uploader_type, uploader_ref,
       state, content_type, byte_size, content_hash, storage_metadata,
       last_error, created_at, updated_at
FROM media_objects
WHERE id = :id
"""
)


def get_media(engine: Engine, media_id: str) -> Optional[dict[str, Any]]:
    """按 id 读取媒体元数据行；不存在返回 None。"""
    with engine.connect() as conn:
        row = conn.execute(_SELECT_MEDIA, {"id": media_id}).mappings().first()
    return dict(row) if row is not None else None
