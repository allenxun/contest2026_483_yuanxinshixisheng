"""结果图归档：算法输出图 → 受控 T11 ``assessment_result`` 行 + 存储对象。

协议（DD §8.4 / §9.2；oracle N1 + F1 + G1）：

* **预校验（无副作用）**：逐图校验并算 ``content_hash=sha256`` / ``byte_size`` /
  ``content_type``；单次调用内 ``provider_ref`` 重复 → 终态
  ``PROVIDER_CONTRACT_VIOLATION``（在任何 DB/存储副作用之前）。
* **tx1（单连接）**：``engine.begin()`` 内先取**事务级** advisory lock
  ``pg_advisory_xact_lock(hashtextextended('d:result-archive:'||aid||':'||pv,0))``，
  再按 ``assessment_id + photo_version + provider_ref`` 读既有行并判定：
  - 无行 → INSERT pending（持久化预期 content_type/byte_size/content_hash）→ COMMIT；
  - available → 仅当 content_type+byte_size+content_hash **全匹配**才复用（对象已是
    同字节，完全跳过 put）；任一不匹配 → 终态 ``PROVIDER_CONTRACT_VIOLATION``（不 put、不改行）；
  - pending 且已持久化 hash → 必须相同，否则终态拒绝；相同 → 进入 put；
  - pending 且 ``content_hash IS NULL``（legacy）→ **在 tx1 内认领摘要**
    （``UPDATE ... content_hash=:h WHERE id=:id AND content_hash IS NULL``）；0 行则
    复读比对（available 全匹配→复用；否则不匹配→终态），关闭 legacy 并发发散窗口；
  - 其它状态 → 终态。
* **put（任何事务之外，不持连接）**：``storage.put(object_key, data, content_type)``
  （真实 OSS 写真实 Content-Type/Content-Length）。不变式：
  任何到达 put 的调用都已通过 tx1 摘要一致 ⇒ 同一 ref 的并发 put 写入**相同字节**到
  同一 key ⇒ 交错无害。put 失败 → pending 行保留；瞬时（网络/5xx）→ 可重试
  ``RESULT_ARCHIVE_FAILED``（terminal=False），配置错误（凭据/权限/4xx）→ 终态
  ``RESULT_ARCHIVE_FAILED``（terminal=True）。
* **tx2（单连接，短事务）**：D handler 内走 :func:`fenced_business_tx` 租约围栏，
  ``UPDATE ... state='available' WHERE id=:id AND state='pending'``（写入全元数据）；
  0 行 → 复读要求 available + 同 object_key + content_type/byte_size/content_hash
  **全匹配**，否则终态 ``PROVIDER_CONTRACT_VIOLATION``；行消失 → 可重试。

**连接纪律（G1 修复）**：一次 ``archive_result_images`` 在任一时刻至多持 **一根**
池连接（tx1 → 释放 → 无连接的 put → tx2 → 释放），且**绝不在任何 DB 事务内做存储
I/O**。此前版本用专用连接跨 tx1→put→tx2 持会话级 advisory lock，默认
``pool_size=5``/``max_overflow=0`` 下同一 cycle 多 assessment 并发会把池耗尽
（每线程还需第二连接）→ 池超时死锁/续租饿死。事务级锁足够：tx1 已把
「建行/校验哈希」按 task+version 串行，digest-first 使「同 ref ⇒ 同字节」成为所有
put 的前置条件，故不需要跨 put 的锁。

**不变式链**：digest-first ⇒ 同 ref 的每次 put 都携带同一摘要（否则在 tx1/claim 被
终态拒绝）⇒ 行元数据恒等于对象字节。保证：绝无「有对象无行」；同一 provider_ref 绝
不出现第二行/第二个 key；任一点崩溃后**同字节**重试复用 pending 行与同一 key 收敛，
**不同字节**重试终态拒绝且原行/对象不变。

残留（披露）：终态失败任务遗留的 owned ``pending`` 行仍受当前孤儿规则限制（不清理）
——但**行存在即可被 T11 扫描发现**，非「无行对象」，可接受。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from sqlalchemy import Connection, Engine, text

from ...media.storage import StorageConfigError, build_object_key
from ...runtime.rows import JobRow
from .constants import ALLOWED_RESULT_CONTENT_TYPES, DEFAULT_BUCKET
from .dfence import fenced_business_tx

_SELECT_RESULT_MEDIA = text(
    """
SELECT id, bucket, object_key, state, content_type, byte_size, content_hash, storage_metadata
FROM media_objects
WHERE assessment_id = CAST(:assessment_id AS uuid)
  AND photo_version = :photo_version
  AND purpose = 'assessment_result'
"""
)

# G1：事务级 advisory lock（tx1 内取，随 COMMIT/ROLLBACK 释放）。按 task+version
# 串行「建行/复用/摘要认领」，使同 ref 的任何 put 都持相同摘要；不跨 put 持锁/连接。
_ADVISORY_XACT_LOCK = text(
    """
SELECT pg_advisory_xact_lock(
    hashtextextended(
        'd:result-archive:' || :assessment_id || ':' || CAST(:photo_version AS text), 0
    )
)
"""
)

# pending 行即持久化预期 content_type/byte_size/content_hash（V1 无禁止约束）。
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

# legacy（无 hash 的 pending 行）在 tx1 内认领摘要，关闭并发发散窗口。
_CLAIM_LEGACY_PENDING = text(
    """
UPDATE media_objects
SET content_hash = :content_hash, byte_size = :byte_size, content_type = :content_type,
    updated_at = CURRENT_TIMESTAMP
WHERE id = CAST(:id AS uuid) AND state = 'pending' AND content_hash IS NULL
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
SELECT id, bucket, object_key, state, content_type, byte_size, content_hash
FROM media_objects WHERE id = CAST(:id AS uuid)
"""
)

_SELECT_SOURCE_MEDIA = text(
    "SELECT id, bucket, object_key, state FROM media_objects WHERE id = CAST(:id AS uuid)"
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


def _bucket_for(storage: Any) -> str:
    """T11 ``media_objects.bucket`` 取值：优先存储适配器配置（aliyun_oss 真实桶），
    否则回退既有默认 ``mvp-media``（文件系统替身/测试，保持既有行为）。

    这样 ``aliyun_oss`` 模式下 DB 记录与真实 OSS 桶一致（跨语言一致性修复；
    Java 侧默认桶见报告，需 Java lane 配合对齐）。
    """
    bucket = getattr(storage, "bucket_name", None)
    if isinstance(bucket, str) and bucket:
        return bucket
    return DEFAULT_BUCKET


#: bucket 不一致的终态配置错误消息：只说明来源列/配置键并声明取值省略，
#: **绝不**输出实际桶名（日志卫生：桶名按本仓约定不视为凭据，但此处按任务要求省略）。
_BUCKET_MISMATCH_MESSAGE = (
    "media_objects.bucket does not match worker configured storage bucket"
    " (column=media_objects.bucket, config=storage.bucket_name; values omitted)"
)


def _assert_bucket_matches(row_bucket: Any, configured_bucket: str) -> None:
    """只读校验：T11 行记录的桶必须等于 worker 实际配置的桶。

    不一致 → 终态 :class:`StorageConfigError`（避免静默按 objectKey 去**另一个桶**
    读写）。**只校验、不改写 T11、不改业务判定**。消息不含桶名。
    """
    if str(row_bucket) != configured_bucket:
        raise StorageConfigError(_BUCKET_MISMATCH_MESSAGE)


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


def _row_matches(
    row: Any,
    *,
    content_type: str,
    byte_size: int,
    content_hash: str,
    object_key: Optional[str] = None,
    bucket: Optional[str] = None,
) -> bool:
    if (
        row.get("content_type") != content_type
        or row.get("byte_size") != byte_size
        or row.get("content_hash") != content_hash
    ):
        return False
    if object_key is not None and str(row.get("object_key")) != object_key:
        return False
    if bucket is not None and str(row.get("bucket")) != bucket:
        return False
    return True


def _claim_or_reuse(
    engine: Engine,
    *,
    environment: str,
    bucket: str,
    assessment_id: str,
    photo_version: int,
    ref: str,
    content_type: str,
    byte_size: int,
    content_hash: str,
) -> tuple[str, str, str]:
    """tx1：事务级锁下判定复用/建行/认领；返回 ``(media_id, object_key, "reuse"|"put")``。

    单连接、单事务；任一内容发散 → 终态 :class:`ArchiveError`（整体回滚）。
    """
    with engine.begin() as conn:
        conn.execute(
            _ADVISORY_XACT_LOCK,
            {"assessment_id": assessment_id, "photo_version": int(photo_version)},
        )
        by_ref = _load_by_ref_conn(conn, assessment_id, photo_version)
        existing = by_ref.get(ref)
        if existing is None:
            media_id = str(uuid.uuid4())
            object_key = build_object_key(environment, "assessment_result", media_id)
            meta = {"schema_version": 1, "provider_ref": ref}
            conn.execute(
                _INSERT_RESULT_MEDIA,
                {
                    "id": media_id,
                    "bucket": bucket,
                    "object_key": object_key,
                    "assessment_id": assessment_id,
                    "photo_version": int(photo_version),
                    "content_type": content_type,
                    "byte_size": byte_size,
                    "content_hash": content_hash,
                    "storage_metadata": _json(meta),
                },
            )
            return media_id, object_key, "put"

        # 只读校验：既有结果行记录桶必须等于当前配置桶，否则不得按 objectKey 去
        # 另一个桶复用/覆盖（终态配置错误，不 put、不改行）。
        _assert_bucket_matches(existing.get("bucket"), bucket)

        media_id = str(existing["id"])
        object_key = str(existing["object_key"])
        state = existing.get("state")
        if state == "available":
            if _row_matches(
                existing,
                content_type=content_type,
                byte_size=byte_size,
                content_hash=content_hash,
            ):
                return media_id, object_key, "reuse"
            raise _contract_violation(
                "available result media content diverges from provider output"
            )
        if state != "pending":
            raise _contract_violation("result media row in unexpected state")

        persisted = existing.get("content_hash")
        if persisted is None:
            # legacy NULL-hash：在 tx1 内认领摘要（并发由 advisory xact lock 串行）
            res = conn.execute(
                _CLAIM_LEGACY_PENDING,
                {
                    "id": media_id,
                    "content_type": content_type,
                    "byte_size": byte_size,
                    "content_hash": content_hash,
                },
            )
            if res.rowcount > 0:
                return media_id, object_key, "put"
            again = conn.execute(_SELECT_MEDIA_BY_ID, {"id": media_id}).mappings().first()
            if again is None:
                raise ArchiveError(
                    "RESULT_ARCHIVE_FAILED",
                    "result media row vanished during claim",
                    terminal=False,
                )
            if again["state"] == "available":
                if _row_matches(
                    again,
                    content_type=content_type,
                    byte_size=byte_size,
                    content_hash=content_hash,
                    bucket=bucket,
                ):
                    return media_id, object_key, "reuse"
                raise _contract_violation(
                    "available result media content diverges from provider output"
                )
            if again["content_hash"] is not None and again["content_hash"] == content_hash:
                return media_id, object_key, "put"
            raise _contract_violation(
                "pending result media bytes diverge from provider output"
            )
        if persisted != content_hash:
            raise _contract_violation(
                "pending result media bytes diverge from provider output"
            )
        return media_id, object_key, "put"


def _archive_one(
    engine: Engine,
    storage: Any,
    *,
    job: Optional[JobRow],
    environment: str,
    bucket: str,
    assessment_id: str,
    photo_version: int,
    ref: str,
    caption: str,
    data: bytes,
    content_type: str,
    byte_size: int,
    content_hash: str,
) -> dict[str, Any]:
    try:
        media_id, object_key, decision = _claim_or_reuse(
            engine,
            environment=environment,
            bucket=bucket,
            assessment_id=assessment_id,
            photo_version=photo_version,
            ref=ref,
            content_type=content_type,
            byte_size=byte_size,
            content_hash=content_hash,
        )
    except StorageConfigError as exc:
        # 既有行记录桶与配置桶不一致等配置错误：归档路径统一映射为**终态**
        # ArchiveError（不 put、不改行；不得伪装成可重试的瞬时故障）。
        raise ArchiveError(
            "RESULT_ARCHIVE_FAILED", "storage configuration error", terminal=True
        ) from exc
    if decision == "reuse":
        return {"media_id": media_id, "caption": caption, "content_type": content_type}

    # 锁外上传（不持任何连接）：同 ref put 均持相同摘要 ⇒ 交错无害。
    # 传入真实 content_type（OSS put 写真实 Content-Type/Content-Length）。
    try:
        storage.put(object_key, data, content_type=content_type)
    except StorageConfigError as exc:
        # 凭据/权限/签名/参数类配置错误：重试不可恢复 → 终态（fail-closed）。
        # 消息不回显任何凭据/取值。
        raise ArchiveError(
            "RESULT_ARCHIVE_FAILED", "storage put failed: configuration error", terminal=True
        ) from exc
    except Exception as exc:
        # 瞬时故障（网络/超时/5xx）保持既有可重试路径（terminal=False）。
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
            if again["state"] != "available" or not _row_matches(
                again,
                content_type=content_type,
                byte_size=byte_size,
                content_hash=content_hash,
                object_key=object_key,
                bucket=bucket,
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

    预校验（无副作用）→ 逐图 tx1(建/复用/摘要认领，单连接) → 锁外 put（不持连接）→
    tx2(fenced promote，单连接)。任一时刻至多持一根池连接。``job`` 非空时 tx2 走租约
    围栏。详模块 docstring。
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

    archived: list[dict[str, Any]] = []
    bucket = _bucket_for(storage)
    for ref, caption, data, content_type, byte_size, content_hash in validated:
        archived.append(
            _archive_one(
                engine,
                storage,
                job=job,
                environment=environment,
                bucket=bucket,
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


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def load_image_bytes(
    engine: Engine, storage: Any, media_ids: dict[str, str]
) -> "dict[str, bytes] | str":
    """按 media_id 读取各视角对象字节；失败返回原因字符串（保持单表读、无 JOIN）。

    **失败语义分层**（不得混淆）：

    - ``StorageConfigError``（桶不一致/权限/凭据/永久配置）→ **向上抛出**，由调用方
      走终态配置错误路径；绝不吞成可重试字符串（避免永久故障无限重试）。
    - 其它存储异常（网络/5xx 瞬时）→ 返回原因字符串，调用方映射为可重试
      ``SOURCE_IMAGE_UNAVAILABLE``。

    **只读 bucket 校验**：T11 行记录的桶必须等于 worker 配置桶才发起对象读取；
    不一致 → 终态 ``StorageConfigError`` 且**不发起任何对象读取**。
    """
    out: dict[str, bytes] = {}
    configured_bucket = _bucket_for(storage)
    for view, media_id in media_ids.items():
        with engine.connect() as conn:
            row = conn.execute(_SELECT_SOURCE_MEDIA, {"id": media_id}).mappings().first()
        if row is None:
            return f"media row missing for view {view}"
        if row["state"] != "available":
            return f"media not available for view {view}"
        # 读取前只读校验桶：绝不静默按 objectKey 去另一个桶读（IMPORTANT 6）。
        _assert_bucket_matches(row["bucket"], configured_bucket)
        try:
            out[view] = storage.get(str(row["object_key"]))
        except StorageConfigError:
            raise  # 配置/权限/永久错误不吞、不转为可重试
        except Exception:  # 存储瞬时不可读 → 可重试
            return f"storage read failed for view {view}"
    return out
