"""结果图归档：算法输出图 → 受控 T11 ``assessment_result`` 行 + 存储对象。

完整归档协议（DD §8.4 / §9.2；oracle N1 + F1）：

* **串行化**：整段归档持 **会话级** advisory lock
  ``pg_advisory_lock(hashtextextended('d:result-archive:'||aid||':'||pv, 0))``，
  在一根**专用连接**上跨 tx1 → put → tx2 全程持有，结束后 ``pg_advisory_unlock``；
  unlock 失败即 ``invalidate()`` 丢弃物理连接，进程崩溃由 PG 自动释放。
  （tx1 作用域的事务级锁不足以覆盖 put/promote，故改会话级。）
* **digest-first**：上传前先由 data 计算 ``content_hash=sha256`` / ``byte_size`` /
  ``content_type``。**V1 检查结论**：``media_objects`` 的 ``content_hash`` 无约束、
  ``byte_size`` 仅 ``IS NULL OR >=0``、``state`` 允许 pending——故 pending INSERT
  即可持久化 expected content_hash/byte_size，作为「同 ref 必同字节」的持久证据。
* **tx1**：按 ``assessment_id + photo_version + provider_ref`` 读既有行；无则生成
  一次 UUID+key 并 INSERT pending（带预期 content_type/byte_size/content_hash）；
  有则按复用规则判定。COMMIT。
* **锁外上传**：``storage.put(object_key, data)``（**任何 DB 事务外**，无存储 I/O
  在事务内）；同一 key 幂等覆盖；put 失败保留 pending 供重试续跑。
* **tx2**：短事务（D handler 内走 :func:`fenced_business_tx` 租约围栏）
  ``UPDATE ... state='available' WHERE id=:id AND state='pending'``；0 行 → 复读并
  做 content_type/byte_size/content_hash/object_key **全匹配**校验。

复用规则（**绝不覆盖发散内容**）：
- available 行：仅当 content_type + byte_size + content_hash **全部匹配**才复用；
  任一不匹配 → 终态 ``PROVIDER_CONTRACT_VIOLATION``（fail-closed，不 put、不改行）。
- pending 行：已持久化 expected hash 时，入参 digest 必须相同，否则终态拒绝；相同 →
  put 同一 key → promote。
- 单次调用内 provider_ref 重复 → 终态 ``PROVIDER_CONTRACT_VIOLATION``（在任何
  存储/DB 副作用之前）。

保证：绝无「有对象无行」；同一 provider_ref 绝不出现第二行/第二个 key；任一点崩溃
后**同字节**重试复用 pending 行与同一 key 收敛，**不同字节**重试终态拒绝且原行/对象
不变；T11 元数据与存储对象字节恒一致。任何归档失败都不发布报告。

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
SELECT id, object_key, state, content_type, byte_size, content_hash, storage_metadata
FROM media_objects
WHERE assessment_id = CAST(:assessment_id AS uuid)
  AND photo_version = :photo_version
  AND purpose = 'assessment_result'
"""
)

# F1：会话级 advisory lock（专用连接跨 tx1→put→tx2 持有），使同 (task,photo_version)
# 的归档全串行，T11 元数据绝不可能与对象字节发散。
_SESSION_LOCK = text(
    """
SELECT pg_advisory_lock(
    hashtextextended(
        'd:result-archive:' || :assessment_id || ':' || CAST(:photo_version AS text), 0
    )
)
"""
)

_SESSION_UNLOCK = text(
    """
SELECT pg_advisory_unlock(
    hashtextextended(
        'd:result-archive:' || :assessment_id || ':' || CAST(:photo_version AS text), 0
    )
)
"""
)

# pending 行即持久化预期 content_type/byte_size/content_hash（V1 无禁止约束，
# 见模块 docstring「V1 检查结论」）。
_INSERT_RESULT_MEDIA = text(
    """
INSERT INTO media_objects (id, bucket, object_key, purpose, assessment_id, photo_version,
                           member_id, uploader_type, state, content_type, byte_size, content_hash,
                           storage_metadata, created_at, updated_at)
VALUES (CAST(:id AS uuid), :bucket, :object_key, 'assessment_result',
        CAST(:assessment_id AS uuid), :photo_version, NULL, 'worker', 'pending',
        :content_type, :byte_size, :content_hash,
        CAST(:storage_metadata AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
    """
SELECT id, object_key, state, content_type, byte_size, content_hash
FROM media_objects WHERE id = CAST(:id AS uuid)
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


def _contract_violation(message: str) -> ArchiveError:
    """provider 输出与既有归档发散 → 终态拒绝（fail-closed，不 put、不改行）。"""
    return ArchiveError("PROVIDER_CONTRACT_VIOLATION", message, terminal=True)


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
    byte_size: int,
    content_hash: str,
) -> tuple[str, str, dict[str, Any]]:
    """tx1：复用既有行或创建 pending 行（持久化预期摘要）；返回 (media_id, key, row)。"""
    with engine.begin() as conn:
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
                "byte_size": byte_size,
                "content_hash": content_hash,
                "storage_metadata": _json(meta),
            },
        )
        return media_id, object_key, {
            "id": media_id,
            "object_key": object_key,
            "state": "pending",
            "content_type": content_type,
            "byte_size": byte_size,
            "content_hash": content_hash,
        }


def _archive_one(
    engine: Engine,
    storage: Any,
    *,
    job: Optional[JobRow],
    environment: str,
    assessment_id: str,
    photo_version: int,
    ref: str,
    caption: str,
    data: bytes,
    content_type: str,
    byte_size: int,
    content_hash: str,
) -> dict[str, Any]:
    media_id, object_key, row = _ensure_pending_row(
        engine,
        environment=environment,
        assessment_id=assessment_id,
        photo_version=photo_version,
        ref=ref,
        content_type=content_type,
        byte_size=byte_size,
        content_hash=content_hash,
    )
    state = row.get("state")
    if state == "available":
        if (
            row.get("content_type") == content_type
            and row.get("byte_size") == byte_size
            and row.get("content_hash") == content_hash
        ):
            return {"media_id": media_id, "caption": caption, "content_type": content_type}
        raise _contract_violation("available result media content diverges from provider output")
    if state != "pending":
        raise _contract_violation("result media row in unexpected state")
    persisted = row.get("content_hash")
    if persisted is not None and persisted != content_hash:
        raise _contract_violation("pending result media bytes diverge from provider output")

    # 锁外上传（任何 DB 事务之外）：同一 key 幂等覆盖；失败保留 pending 供重试续跑。
    try:
        storage.put(object_key, data)
    except Exception as exc:
        raise ArchiveError(
            "RESULT_ARCHIVE_FAILED", "storage put failed", terminal=False
        ) from exc

    meta = {"schema_version": 1, "provider_ref": ref}
    with _promote_tx(engine, job) as conn:
        res = conn.execute(
            _PROMOTE_PENDING_MEDIA,
            {
                "id": media_id,
                "content_type": content_type,
                "byte_size": byte_size,
                "content_hash": content_hash,
                "storage_metadata": _json(meta),
            },
        )
        if res.rowcount == 0:
            again = conn.execute(_SELECT_MEDIA_BY_ID, {"id": media_id}).mappings().first()
            if again is None:
                raise ArchiveError(
                    "RESULT_ARCHIVE_FAILED",
                    "result media row vanished during promotion",
                    terminal=False,
                )
            if (
                again["state"] != "available"
                or str(again["object_key"]) != object_key
                or again["content_type"] != content_type
                or again["byte_size"] != byte_size
                or again["content_hash"] != content_hash
            ):
                raise _contract_violation("result media promotion diverged concurrently")
    return {"media_id": media_id, "caption": caption, "content_type": content_type}


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
    """归档结果图（保序返回 ``[{"media_id","caption","content_type"}]``）。

    预校验（无副作用）→ 会话锁 → 逐图 tx1(建/复用) → 锁外 put → tx2(promote)。
    ``job`` 非空时 tx2 走租约围栏。详模块 docstring。
    """
    # --- 预校验（任何存储/DB 副作用之前）---
    validated: list[tuple[str, str, bytes, str, int, str]] = []
    seen_refs: set[str] = set()
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
        if ref in seen_refs:
            raise _contract_violation("duplicate provider_ref within one result set")
        seen_refs.add(ref)
        validated.append(
            (ref, caption, data, content_type, len(data), hashlib.sha256(data).hexdigest())
        )

    lock_params = {"assessment_id": assessment_id, "photo_version": int(photo_version)}
    with engine.connect() as lock_conn:
        lock_conn.execute(_SESSION_LOCK, lock_params)
        lock_conn.commit()  # 会话锁跨事务保持
        try:
            archived: list[dict[str, Any]] = []
            for ref, caption, data, content_type, byte_size, content_hash in validated:
                archived.append(
                    _archive_one(
                        engine,
                        storage,
                        job=job,
                        environment=environment,
                        assessment_id=assessment_id,
                        photo_version=photo_version,
                        ref=ref,
                        caption=caption,
                        data=data,
                        content_type=content_type,
                        byte_size=byte_size,
                        content_hash=content_hash,
                    )
                )
            return archived
        finally:
            try:
                lock_conn.execute(_SESSION_UNLOCK, lock_params)
                lock_conn.commit()
            except Exception:
                # 解锁失败：丢弃物理连接，交由 PG 断连释放会话锁（绝不泄漏到池复用）
                lock_conn.invalidate()


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
