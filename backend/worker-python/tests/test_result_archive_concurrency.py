"""结果图归档两阶段 + 并发证据（oracle N1）。

存储不可随 PG 事务回滚，故须两阶段：tx1 持 advisory lock 建/复用 pending 行 →
锁外 put 同一 key → tx2 提升 available。本文件证明：
- 并发同 (task,version,ref) → 恰一行一对象、同一 media_id；
- put 后提升前崩溃 → 对象与 pending 行俱在，重试复用同一行/key 收敛；
- put 失败 → pending 行保留，重试成功；
- tx1 后 put 前崩溃 → 行已持久化，重试补 put 收敛。
"""
from __future__ import annotations

import hashlib
import threading
from typing import Any

import pytest
from sqlalchemy import Engine, text

from d_support import PNG_BYTES, clean_d_tables, fetch_result_media, seed_assessment
from mvp_worker.handlers.dshared import dmedia
from mvp_worker.handlers.dshared.dmedia import ArchiveError, archive_result_images
from mvp_worker.media.storage import FilesystemStorageDouble


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


def _seed(engine: Engine, tmp_path: Any) -> tuple[Any, str]:
    storage = FilesystemStorageDouble(tmp_path / "arch")
    aid = seed_assessment(
        engine, status="analyzing", current_photo_version=1, processing_revision=2
    )
    return storage, aid


def _images() -> list[dict[str, Any]]:
    return [{"ref": "skin-result-1", "caption": "c1", "bytes": PNG_BYTES}]


def _object_key(engine: Engine, media_id: str) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(
                text("SELECT object_key FROM media_objects WHERE id = CAST(:id AS uuid)"),
                {"id": media_id},
            ).scalar_one()
        )


def _files(tmp_path: Any) -> list[Any]:
    return [p for p in (tmp_path / "arch").rglob("*") if p.is_file()]


def test_archive_concurrent_same_ref_single_row_and_object(
    engine: Engine, tmp_path: Any
) -> None:
    storage, aid = _seed(engine, tmp_path)
    result_images = _images()

    barrier = threading.Barrier(2)
    media_ids: list[str] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=15)
            archived = archive_result_images(
                engine,
                storage,
                environment="dev",
                assessment_id=aid,
                photo_version=1,
                result_images=result_images,
                max_bytes=10_000_000,
            )
            media_ids.append(str(archived[0]["media_id"]))
        except BaseException as exc:  # noqa: BLE001 - 记录并断言为空
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(media_ids) == 2
    assert media_ids[0] == media_ids[1]  # 复用而非各自新建

    rows = fetch_result_media(engine, aid, 1)
    assert len(rows) == 1
    assert rows[0]["state"] == "available"
    assert str(rows[0]["id"]) == media_ids[0]
    assert len(_files(tmp_path)) == 1  # 恰一个存储对象


def test_archive_crash_after_put_converges_same_row_and_key(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """put 成功、tx2 提升前崩溃 → 对象 + pending 行俱在；重试复用同一行/key 收敛。"""
    storage, aid = _seed(engine, tmp_path)
    result_images = _images()
    real_promote = dmedia._promote_tx

    def crash(_engine: Any, _job: Any) -> Any:
        raise RuntimeError("simulated crash after put before promote")

    monkeypatch.setattr(dmedia, "_promote_tx", crash)
    with pytest.raises(RuntimeError):
        archive_result_images(
            engine, storage, environment="dev", assessment_id=aid,
            photo_version=1, result_images=result_images, max_bytes=10_000_000,
        )

    rows = fetch_result_media(engine, aid, 1)
    assert len(rows) == 1 and rows[0]["state"] == "pending"
    mid = str(rows[0]["id"])
    key = _object_key(engine, mid)
    assert storage.exists(key)  # 对象已上传（不因 PG 回滚而消失）
    assert len(_files(tmp_path)) == 1

    monkeypatch.setattr(dmedia, "_promote_tx", real_promote)
    archived = archive_result_images(
        engine, storage, environment="dev", assessment_id=aid,
        photo_version=1, result_images=result_images, max_bytes=10_000_000,
    )
    assert str(archived[0]["media_id"]) == mid  # 复用同一行
    assert _object_key(engine, mid) == key  # 复用同一 key
    rows2 = fetch_result_media(engine, aid, 1)
    assert len(rows2) == 1 and rows2[0]["state"] == "available"
    assert len(_files(tmp_path)) == 1


def test_archive_put_failure_retains_pending_then_retry_succeeds(
    engine: Engine, tmp_path: Any
) -> None:
    """put 失败 → pending 行保留（意图持久化）；重试复用同一行/key 后 available。"""
    storage, aid = _seed(engine, tmp_path)

    class _FailFirstStorage:
        def __init__(self) -> None:
            self._remaining = 1

        def put(self, object_key: str, data: bytes) -> None:
            if self._remaining > 0:
                self._remaining -= 1
                raise RuntimeError("injected put failure")
            storage.put(object_key, data)

        def get(self, object_key: str) -> bytes:
            return storage.get(object_key)

        def delete(self, object_key: str) -> None:
            storage.delete(object_key)

        def exists(self, object_key: str) -> bool:
            return storage.exists(object_key)

    with pytest.raises(ArchiveError) as excinfo:
        archive_result_images(
            engine, _FailFirstStorage(), environment="dev", assessment_id=aid,
            photo_version=1, result_images=_images(), max_bytes=10_000_000,
        )
    assert excinfo.value.terminal is False

    rows = fetch_result_media(engine, aid, 1)
    assert len(rows) == 1 and rows[0]["state"] == "pending"
    mid = str(rows[0]["id"])
    key = _object_key(engine, mid)

    archived = archive_result_images(
        engine, storage, environment="dev", assessment_id=aid,
        photo_version=1, result_images=_images(), max_bytes=10_000_000,
    )
    assert str(archived[0]["media_id"]) == mid
    assert _object_key(engine, mid) == key
    rows2 = fetch_result_media(engine, aid, 1)
    assert len(rows2) == 1 and rows2[0]["state"] == "available"
    assert len(_files(tmp_path)) == 1


def test_archive_crash_before_put_converges_on_retry(
    engine: Engine, tmp_path: Any
) -> None:
    """tx1 后 put 前崩溃（模拟为不 put）→ pending 行已持久化；重试补 put 收敛。"""
    storage, aid = _seed(engine, tmp_path)

    class _SimulatedCrash(BaseException):
        pass

    class _CrashBeforePutStorage:
        def put(self, object_key: str, data: bytes) -> None:
            raise _SimulatedCrash()

        def get(self, object_key: str) -> bytes:
            raise AssertionError("unused")

        def delete(self, object_key: str) -> None:
            pass

        def exists(self, object_key: str) -> bool:
            return False

    with pytest.raises(_SimulatedCrash):
        archive_result_images(
            engine, _CrashBeforePutStorage(), environment="dev", assessment_id=aid,
            photo_version=1, result_images=_images(), max_bytes=10_000_000,
        )

    rows = fetch_result_media(engine, aid, 1)
    assert len(rows) == 1 and rows[0]["state"] == "pending"  # tx1 已提交
    mid = str(rows[0]["id"])
    key = _object_key(engine, mid)
    assert not storage.exists(key)  # 尚未上传

    archived = archive_result_images(
        engine, storage, environment="dev", assessment_id=aid,
        photo_version=1, result_images=_images(), max_bytes=10_000_000,
    )
    assert str(archived[0]["media_id"]) == mid
    assert _object_key(engine, mid) == key
    rows2 = fetch_result_media(engine, aid, 1)
    assert len(rows2) == 1 and rows2[0]["state"] == "available"
    assert storage.exists(key)
    assert len(_files(tmp_path)) == 1


# ---------------------------------------------------- F1 divergent-content


def test_archive_duplicate_ref_terminal_before_side_effects(
    engine: Engine, tmp_path: Any
) -> None:
    """F1：单次调用内 provider_ref 重复 → 终态 PROVIDER_CONTRACT_VIOLATION，零副作用。"""
    storage, aid = _seed(engine, tmp_path)
    duplicate = [
        {"ref": "dup", "caption": "a", "bytes": PNG_BYTES},
        {"ref": "dup", "caption": "b", "bytes": PNG_BYTES},
    ]
    with pytest.raises(ArchiveError) as excinfo:
        archive_result_images(
            engine, storage, environment="dev", assessment_id=aid,
            photo_version=1, result_images=duplicate, max_bytes=10_000_000,
        )
    assert excinfo.value.code == "PROVIDER_CONTRACT_VIOLATION"
    assert excinfo.value.terminal is True
    assert fetch_result_media(engine, aid, 1) == []
    assert _files(tmp_path) == []


def test_archive_available_different_bytes_terminal_original_untouched(
    engine: Engine, tmp_path: Any
) -> None:
    """F1：已 available 的 ref 收到不同字节 → 终态拒绝；原行/对象字节不变。"""
    storage, aid = _seed(engine, tmp_path)
    data_a = PNG_BYTES
    data_b = PNG_BYTES + b"\x01\x02\x03"  # 同 MIME（PNG 头），不同字节/大小

    arch = archive_result_images(
        engine, storage, environment="dev", assessment_id=aid,
        photo_version=1, result_images=[{"ref": "r1", "caption": "a", "bytes": data_a}],
        max_bytes=10_000_000,
    )
    mid = str(arch[0]["media_id"])
    key = _object_key(engine, mid)

    with pytest.raises(ArchiveError) as excinfo:
        archive_result_images(
            engine, storage, environment="dev", assessment_id=aid,
            photo_version=1, result_images=[{"ref": "r1", "caption": "a2", "bytes": data_b}],
            max_bytes=10_000_000,
        )
    assert excinfo.value.code == "PROVIDER_CONTRACT_VIOLATION"
    assert excinfo.value.terminal is True

    rows = fetch_result_media(engine, aid, 1)
    assert len(rows) == 1 and rows[0]["state"] == "available"
    assert rows[0]["content_hash"] == hashlib.sha256(data_a).hexdigest()
    assert rows[0]["byte_size"] == len(data_a)
    assert rows[0]["content_type"] == "image/png"
    assert storage.get(key) == data_a  # 对象字节未被覆盖
    assert _object_key(engine, mid) == key
    assert len(_files(tmp_path)) == 1


def test_archive_concurrent_same_ref_different_bytes_one_winner(
    engine: Engine, tmp_path: Any
) -> None:
    """F1：并发同 ref 不同字节 → 恰一个赢家；T11 hash 与存储对象字节一致，输家终态拒绝。"""
    storage, aid = _seed(engine, tmp_path)
    data_a = PNG_BYTES
    data_b = PNG_BYTES + b"\x01\x02\x03"
    barrier = threading.Barrier(2)
    outcomes: list[tuple[str, str]] = []

    def worker(data: bytes) -> None:
        try:
            barrier.wait(timeout=15)
            arch = archive_result_images(
                engine, storage, environment="dev", assessment_id=aid,
                photo_version=1,
                result_images=[{"ref": "r1", "caption": "c", "bytes": data}],
                max_bytes=10_000_000,
            )
            outcomes.append(("ok", str(arch[0]["media_id"])))
        except ArchiveError as exc:
            outcomes.append(("reject", exc.code))

    threads = [
        threading.Thread(target=worker, args=(data_a,)),
        threading.Thread(target=worker, args=(data_b,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    ok = [o for o in outcomes if o[0] == "ok"]
    rejected = [o for o in outcomes if o[0] == "reject"]
    assert len(ok) == 1
    assert len(rejected) == 1 and rejected[0][1] == "PROVIDER_CONTRACT_VIOLATION"

    rows = fetch_result_media(engine, aid, 1)
    assert len(rows) == 1 and rows[0]["state"] == "available"
    mid = str(rows[0]["id"])
    stored = storage.get(_object_key(engine, mid))
    # T11 元数据必须与存储对象字节一致（赢家字节）
    assert stored in (data_a, data_b)
    assert rows[0]["content_hash"] == hashlib.sha256(stored).hexdigest()
    assert rows[0]["byte_size"] == len(stored)
    assert rows[0]["content_type"] == "image/png"
    assert len(_files(tmp_path)) == 1
