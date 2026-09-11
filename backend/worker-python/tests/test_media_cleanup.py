"""``media.cleanup`` handler 覆盖：范围守卫、引用核查、两段式删除、崩溃恢复（裁定 5）。"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from conftest import enqueue, fetch_job
from d_support import (
    clean_d_tables,
    count_jobs_by_dedup,
    fetch_job_full_by_dedup,
    make_ctx,
    run_claimed,
    seed_assessment,
    seed_execution,
    seed_idempotency,
    seed_member,
    seed_media,
    seed_microcrystal,
    seed_plan,
)
from mvp_worker.handlers import media_cleanup as media_cleanup_module
from mvp_worker.handlers.media_cleanup import (
    discover_and_enqueue_orphans,
    handler as cleanup_handler,
)
from mvp_worker.media.storage import FilesystemStorageDouble, StorageError
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.expire import release_claim


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


def _enqueue_cleanup(engine: Engine, media_id: str, rev: int = 1) -> str:
    jid, _ = enqueue(
        engine,
        job_type="media.cleanup",
        dedup_key=f"media:{media_id}:cleanup:{rev}",
        owner_type="media",
        owner_id=media_id,
        input_revision=rev,
        payload={
            "schema_version": 1,
            "media_object_id": media_id,
            "cleanup_revision": str(rev),
        },
    )
    return jid


def _state(engine: Engine, media_id: str) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(
                text("SELECT state FROM media_objects WHERE id = CAST(:id AS uuid)"),
                {"id": media_id},
            ).scalar_one()
        )


def _run(engine: Engine, jid: str, storage: Any) -> tuple[str, Any, Any]:
    return run_claimed(engine, cleanup_handler, jid, extras={"storage": storage})


def create_db_engine_with_lock_timeout(dsn: str, lock_timeout_ms: int = 300) -> Any:
    """测试专用引擎：连接级 ``lock_timeout``（``SET`` 会被 SQLAlchemy 回滚，故用
    ``connect_args`` 在连接建立时设置，保证 GUC 持久到会话）。"""
    url = make_url(dsn)
    if url.drivername in ("postgresql", "postgres"):
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(
        url,
        pool_size=2,
        max_overflow=0,
        connect_args={"options": f"-c lock_timeout={int(lock_timeout_ms)}"},
    )


class _FaultyDeleteStorage:
    def __init__(self, inner: FilesystemStorageDouble, failures: int = 1) -> None:
        self._inner = inner
        self._remaining = failures

    def delete(self, object_key: str) -> None:
        if self._remaining > 0:
            self._remaining -= 1
            raise StorageError("injected delete failure")
        self._inner.delete(object_key)

    def exists(self, object_key: str) -> bool:
        return self._inner.exists(object_key)

    def put(self, object_key: str, data: bytes) -> None:
        self._inner.put(object_key, data)

    def get(self, object_key: str) -> bytes:
        return self._inner.get(object_key)


def test_cleanup_orphan_available_deleted(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="available")
    jid = _enqueue_cleanup(engine, mid)
    status, exc, _ = _run(engine, jid, storage)
    assert status == "succeeded" and exc is None
    assert _state(engine, mid) == "deleted"
    assert not storage.exists(key)
    assert fetch_job(engine, jid)["status"] == "succeeded"


def test_cleanup_failed_row_deleted(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="failed")
    jid = _enqueue_cleanup(engine, mid)
    status, exc, _ = _run(engine, jid, storage)
    assert status == "succeeded" and exc is None
    assert _state(engine, mid) == "deleted"
    assert not storage.exists(key)


def test_cleanup_processor_active_retryable(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    tid = seed_idempotency(engine, status="processing", lease_until_seconds=300)
    mid, key = seed_media(engine, storage, state="available", request_id=tid)
    jid = _enqueue_cleanup(engine, mid)
    status, exc, _ = _run(engine, jid, storage)
    assert status == "failed" and exc is not None
    assert exc.code == "PROCESSOR_ACTIVE" and exc.retryable is True
    assert _state(engine, mid) == "available"  # unchanged
    assert storage.exists(key)
    assert fetch_job(engine, jid)["status"] == "queued"


def test_cleanup_t13_succeeded_unowned_deleted(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    tid = seed_idempotency(engine, status="succeeded")
    mid, key = seed_media(engine, storage, state="available", request_id=tid)
    jid = _enqueue_cleanup(engine, mid)
    status, exc, _ = _run(engine, jid, storage)
    assert status == "succeeded" and exc is None
    assert _state(engine, mid) == "deleted"
    assert not storage.exists(key)


def test_cleanup_referenced_via_t05_photo_versions(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="available")
    seed_assessment(
        engine,
        photo_versions={
            "schema_version": 1,
            "versions": [
                {
                    "version": 1,
                    "images": {"front": mid, "left": mid, "right": mid},
                    "quality": {"status": "accepted", "required_views": []},
                }
            ],
        },
    )
    jid = _enqueue_cleanup(engine, mid)
    status, exc, _ = _run(engine, jid, storage)
    assert status == "failed" and exc is not None
    assert exc.code == "MEDIA_REFERENCED" and exc.retryable is False
    assert _state(engine, mid) == "available"
    assert storage.exists(key)


def test_cleanup_referenced_via_member_identity_summary(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="available")
    seed_member(
        engine,
        identity_summary={"schema_version": 1, "reference_media": {"front": mid}},
    )
    jid = _enqueue_cleanup(engine, mid)
    status, exc, _ = _run(engine, jid, storage)
    assert status == "failed" and exc is not None
    assert exc.code == "MEDIA_REFERENCED" and exc.retryable is False
    assert _state(engine, mid) == "available"
    assert storage.exists(key)


def test_cleanup_referenced_via_execution_latest_verification(
    engine: Engine, tmp_path: Any
) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="available")
    aid = seed_assessment(engine)
    member_id = seed_member(engine, assessment_id=aid)
    plan_id = seed_plan(engine, assessment_id=aid, member_id=member_id)
    micro_id = seed_microcrystal(engine)
    seed_execution(
        engine,
        plan_id=plan_id,
        member_id=member_id,
        microcrystal_id=micro_id,
        assessment_id=aid,
        request_id=seed_idempotency(engine),
        latest_verification={"schema_version": 1, "media_ref": mid},
    )
    jid = _enqueue_cleanup(engine, mid)
    status, exc, _ = _run(engine, jid, storage)
    assert status == "failed" and exc is not None
    assert exc.code == "MEDIA_REFERENCED" and exc.retryable is False
    assert _state(engine, mid) == "available"
    assert storage.exists(key)


def test_cleanup_owned_row_terminal(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    aid = seed_assessment(engine)
    mid, key = seed_media(engine, storage, state="available", assessment_id=aid)
    jid = _enqueue_cleanup(engine, mid)
    status, exc, _ = _run(engine, jid, storage)
    assert status == "failed" and exc is not None
    assert exc.code == "MEDIA_REFERENCED" and exc.retryable is False
    assert _state(engine, mid) == "available"
    assert storage.exists(key)


def test_cleanup_rerun_on_deleted_noop(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, _key = seed_media(engine, storage, state="deleted", put_object=False)
    jid = _enqueue_cleanup(engine, mid)
    status, exc, _ = _run(engine, jid, storage)
    assert status == "succeeded" and exc is None
    assert _state(engine, mid) == "deleted"


def test_cleanup_resume_from_deleting(engine: Engine, tmp_path: Any) -> None:
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="deleting")
    jid = _enqueue_cleanup(engine, mid)
    status, exc, _ = _run(engine, jid, storage)
    assert status == "succeeded" and exc is None
    assert _state(engine, mid) == "deleted"
    assert not storage.exists(key)


def test_cleanup_storage_delete_fault_then_retry(engine: Engine, tmp_path: Any) -> None:
    inner = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, inner, state="available")
    faulty = _FaultyDeleteStorage(inner, failures=1)
    jid = _enqueue_cleanup(engine, mid)

    status, exc, _ = _run(engine, jid, faulty)
    assert status == "failed" and exc is not None
    assert exc.code == "STORAGE_DELETE_FAILED" and exc.retryable is True
    assert _state(engine, mid) == "deleting"  # row stays deleting for idempotent resume
    assert inner.exists(key)

    status2, exc2, _ = _run(engine, jid, inner)
    assert status2 == "succeeded" and exc2 is None
    assert _state(engine, mid) == "deleted"
    assert not inner.exists(key)


# ------------------------------------------------- orphan discovery (Item C)


def test_discover_orphan_enqueues_and_cleanup_cycle(engine: Engine, tmp_path: Any) -> None:
    """crash-after-ingest 孤儿：发现 → 恰好 1 job → 完整清理 → 再发现 0 新任务。"""
    storage = FilesystemStorageDouble(tmp_path / "s")
    tid = seed_idempotency(engine, status="succeeded")
    mid, key = seed_media(engine, storage, state="available", request_id=tid)
    assert storage.exists(key)

    assert discover_and_enqueue_orphans(engine) == 1
    dedup = f"media:{mid}:cleanup:1"
    assert count_jobs_by_dedup(engine, dedup) == 1
    job = fetch_job_full_by_dedup(engine, dedup)
    assert job["job_type"] == "media.cleanup"
    assert job["status"] == "queued"
    assert job["owner_type"] == "media"
    assert str(job["owner_id"]) == mid
    assert int(job["input_revision"]) == 1
    assert job["payload"]["schema_version"] == 1
    assert job["payload"]["media_object_id"] == mid
    assert job["payload"]["cleanup_revision"] == "1"

    # 运行 runtime claim→handle→complete 周期
    status, exc, _ = run_claimed(
        engine, cleanup_handler, str(job["id"]), extras={"storage": storage}
    )
    assert status == "succeeded" and exc is None
    assert _state(engine, mid) == "deleted"
    assert not storage.exists(key)

    # 再发现：行已 deleted 不再是候选 → 0 新任务
    assert discover_and_enqueue_orphans(engine) == 0
    assert count_jobs_by_dedup(engine, dedup) == 1


def test_discover_idempotent_before_cleanup(engine: Engine, tmp_path: Any) -> None:
    """重复发现同一候选：dedup 冲突 → 0 新任务（幂等）。"""
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, _key = seed_media(engine, storage, state="available")
    assert discover_and_enqueue_orphans(engine) == 1
    assert discover_and_enqueue_orphans(engine) == 0
    assert count_jobs_by_dedup(engine, f"media:{mid}:cleanup:1") == 1


def test_discover_skips_referenced_media(engine: Engine, tmp_path: Any) -> None:
    """被 T05.photo_versions 引用的对象绝不入队（安全证明不足不删）。"""
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="available")
    seed_assessment(
        engine,
        photo_versions={
            "schema_version": 1,
            "versions": [
                {
                    "version": 1,
                    "images": {"front": mid, "left": mid, "right": mid},
                    "quality": {"status": "accepted", "required_views": []},
                }
            ],
        },
    )
    assert discover_and_enqueue_orphans(engine) == 0
    assert count_jobs_by_dedup(engine, f"media:{mid}:cleanup:1") == 0
    assert _state(engine, mid) == "available"
    assert storage.exists(key)


def test_discover_skips_live_lease_processor(engine: Engine, tmp_path: Any) -> None:
    """T13 处理者租约仍活跃 → 本轮跳过（不删不入队）。"""
    storage = FilesystemStorageDouble(tmp_path / "s")
    tid = seed_idempotency(engine, status="processing", lease_until_seconds=300)
    mid, key = seed_media(engine, storage, state="available", request_id=tid)
    assert discover_and_enqueue_orphans(engine) == 0
    assert count_jobs_by_dedup(engine, f"media:{mid}:cleanup:1") == 0
    assert _state(engine, mid) == "available"
    assert storage.exists(key)


def test_discover_expired_processing_t13_enqueues(engine: Engine, tmp_path: Any) -> None:
    """T13 processing 但租约已过期（崩溃残留）→ 可发现入队。"""
    storage = FilesystemStorageDouble(tmp_path / "s")
    tid = seed_idempotency(engine, status="processing", lease_until_seconds=-5)
    mid, _key = seed_media(engine, storage, state="available", request_id=tid)
    assert discover_and_enqueue_orphans(engine) == 1
    assert count_jobs_by_dedup(engine, f"media:{mid}:cleanup:1") == 1


def test_discover_failed_orphan_enqueued_and_cleaned(engine: Engine, tmp_path: Any) -> None:
    """failed 状态的无归属孤儿同样被发现，并经完整 claim→handle→complete 清理。"""
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="failed")
    assert storage.exists(key)

    assert discover_and_enqueue_orphans(engine) == 1
    dedup = f"media:{mid}:cleanup:1"
    assert count_jobs_by_dedup(engine, dedup) == 1
    job = fetch_job_full_by_dedup(engine, dedup)

    status, exc, _ = run_claimed(
        engine, cleanup_handler, str(job["id"]), extras={"storage": storage}
    )
    assert status == "succeeded" and exc is None
    assert _state(engine, mid) == "deleted"
    assert not storage.exists(key)
    # 再发现：行已 deleted 不再是候选 → 0 新任务
    assert discover_and_enqueue_orphans(engine) == 0
    assert count_jobs_by_dedup(engine, dedup) == 1


# --------------------------------------------------------- I2 TOCTOU recheck


def test_cleanup_post_lock_recheck_catches_late_reference(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """I2：引用在**预读之后、加锁之前**出现 → 锁后同事务重扫捕获并 abort。

    通过 monkeypatch ``_load_media``（无锁预读）注入一次已提交的新引用，模拟并发
    受理在本清理事务取得 T11 行锁前提交；若只靠预读（无锁后重扫）就会误删。
    """
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="available")
    aid = seed_assessment(engine, status="queued")
    jid = _enqueue_cleanup(engine, mid)

    original = media_cleanup_module._load_media
    fired = {"done": False}

    def hooked(eng: Engine, media_id: str) -> Any:
        row = original(eng, media_id)
        if not fired["done"] and row is not None and row["state"] != "deleting":
            fired["done"] = True
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE skin_assessments SET photo_versions = CAST(:pv AS jsonb)"
                        " WHERE id = CAST(:a AS uuid)"
                    ),
                    {
                        "pv": json.dumps(
                            {
                                "schema_version": 1,
                                "versions": [{"version": 1, "images": {"front": media_id}}],
                            }
                        ),
                        "a": aid,
                    },
                )
        return row

    monkeypatch.setattr(media_cleanup_module, "_load_media", hooked)

    status, exc, _ = _run(engine, jid, storage)
    assert status == "failed" and exc is not None
    assert exc.code == "MEDIA_REFERENCED" and exc.retryable is False
    assert _state(engine, mid) == "available"  # 未进入 deleting
    assert storage.exists(key)


def test_cleanup_lock_contention_aborts_without_state_change(
    engine: Engine, tmp_path: Any, test_dsn: str
) -> None:
    """I2：受理持 T11 行锁时，清理以短 lock_timeout 安全中止（无过渡、无删除）。"""
    storage = FilesystemStorageDouble(tmp_path / "s")
    mid, key = seed_media(engine, storage, state="available")
    jid = _enqueue_cleanup(engine, mid)
    claims = claim_batch(engine, worker_id="w-d", lease_seconds=60, batch_size=50)
    claim = next(c for c in claims if c.id == jid)
    for other in claims:
        if other.id != jid:
            release_claim(engine, other, worker_id="w-d")

    eng2 = create_db_engine_with_lock_timeout(test_dsn)

    holder = engine.connect()
    tx = holder.begin()
    try:
        # 模拟受理：持有 T11 行锁
        holder.execute(
            text("SELECT id FROM media_objects WHERE id = CAST(:id AS uuid) FOR UPDATE"),
            {"id": mid},
        )
        ctx = make_ctx(eng2, claim, extras={"storage": storage})
        with pytest.raises(Exception) as excinfo:
            cleanup_handler.handle(ctx, claim)
        assert "lock timeout" in str(excinfo.value).lower()
    finally:
        tx.rollback()
        holder.close()
        eng2.dispose()

    assert _state(engine, mid) == "available"  # 无过渡
    assert storage.exists(key)  # 无删除
