# -*- coding: utf-8 -*-
"""项 A（SC-02-09 真实迟到返回）与项 B（SC-02-10 确定性终态失败）—— B 定向测试。

纪律：
- 时序一律经**真实** ``claim_batch``/``recover_expired``/handler/``complete_success``
  围栏路径；不直接改 ``async_jobs``/``skin_assessments`` 业务列伪造状态（仅做初始 fixture seed）；
- 不 sleep 伪造注入、不改业务判定、无任何 HTTP 可开启路径；
- 新旋钮默认关闭、严格值域、登记进 ``DOUBLE_INJECTION_SWITCHES`` 受生产启动守卫覆盖。
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from d_support import (
    DEFAULT_NS,
    clean_d_tables,
    fetch_assessment,
    make_ctx,
    photo_versions_for,
    run_claimed,
    seed_assessment,
    seed_member,
    seed_source_media,
)

from mvp_worker.handlers.assessment_analyze import handler as analyze_handler
from mvp_worker.handlers.dshared.dconfig import (
    DConfig,
    ProviderConfigError,
    assert_no_double_injection_in_production,
    double_injection_overrides,
)
from mvp_worker.handlers.dshared.providers import (
    FaceDouble,
    LateReturnBarrier,
    ProviderUnavailable,
    SkinDouble,
    build_face_port,
)
from mvp_worker.media.storage import FilesystemStorageDouble, build_object_key
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.complete import StaleGeneration, complete_success
from mvp_worker.runtime.expire import recover_expired

_NEW_ENVS = (
    "MVP_D_SKIN_DOUBLE_INVALID",
    "MVP_D_DOUBLE_LATE_BARRIER",
    "MVP_D_DOUBLE_LATE_BARRIER_DIR",
    "MVP_D_DOUBLE_LATE_BARRIER_SHA256",
    "MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


@pytest.fixture(autouse=True)
def _default_new_env_off(monkeypatch: Any) -> None:
    for name in _NEW_ENVS:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------- helpers


def _attach_photo_versions(
    engine: Engine, assessment_id: str, version: int, images: dict[str, str]
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET photo_versions = CAST(:pv AS jsonb)"
                " WHERE id = CAST(:id AS uuid)"
            ),
            {"pv": json.dumps(photo_versions_for(version, images)), "id": assessment_id},
        )


def _enqueue_analyze(engine: Engine, aid: str, rev: int, *, max_attempts: int = 5) -> str:
    jid, _ = enqueue(
        engine,
        job_type="assessment.analyze",
        dedup_key=f"assessment:{aid}:{rev}",
        owner_type="assessment",
        owner_id=aid,
        input_revision=rev,
        payload={
            "schema_version": 1,
            "assessment_id": aid,
            "processing_revision": str(rev),
        },
        max_attempts=max_attempts,
    )
    return jid


def _seed_marked_case(
    engine: Engine, tmp_path: Any, marker: bytes
) -> tuple[FilesystemStorageDouble, str, dict[str, str]]:
    """Seed 一个含**内容可识别标记**的 v1 任务（仅初始 fixture；不伪造时序状态）。"""
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(
        engine, status="queued", current_photo_version=1, processing_revision=1
    )
    images: dict[str, str] = {}
    for index, view in enumerate(("front", "left", "right")):
        mid = str(uuid.uuid4())
        key = build_object_key("dev", "assessment_source", mid)
        data = marker + (b"\x00" * index)
        storage.put(key, data)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO media_objects (id, bucket, object_key, purpose,"
                    " assessment_id, photo_version, state, content_type, byte_size,"
                    " content_hash, uploader_type)"
                    " VALUES (CAST(:id AS uuid), 'mvp-media', :k, 'assessment_source',"
                    " CAST(:a AS uuid), 1, 'available', 'image/png', :bs, :h, 'worker')"
                ),
                {"id": mid, "k": key, "a": aid, "bs": len(data), "h": "0" * 64},
            )
        images[view] = mid
    _attach_photo_versions(engine, aid, 1, images)
    return storage, aid, images


def _wait_file(path: Any, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return path.exists()


def _evidence(label: str, **fields: Any) -> None:
    """opt-in 证据转储（MVP_SEAM_EVIDENCE=1 + pytest -s 时打印实测中间态）。"""
    if os.environ.get("MVP_SEAM_EVIDENCE") == "1":
        print("EVIDENCE", label, json.dumps(fields, ensure_ascii=False, default=str))


# ===================================================== 项 A：SC-02-09 真实迟到返回


def test_sc0209_lease_expiry_takeover_fences_stale_late_return(
    engine: Engine, tmp_path: Any
) -> None:
    """旧 provider 在飞 → 租约过期 → 接管者提交 needs_retake → 释放旧 provider 的
    迟到结果被既有租约围栏拒绝，绝不覆盖接管者结果。

    全程经真实 claim/recover/handle/complete 围栏；A 的旧结果在 barrier 前已算出。
    """
    marker = b"late-return-" + uuid.uuid4().bytes
    sha = hashlib.sha256(marker).hexdigest()
    barrier_dir = tmp_path / "barrier"
    storage, aid, _images = _seed_marked_case(engine, tmp_path, marker)
    ref = str(uuid.uuid4())
    seed_member(engine, ns=DEFAULT_NS, ref=ref, assessment_id=aid)
    jid = _enqueue_analyze(engine, aid, 1, max_attempts=5)

    barrier = LateReturnBarrier(
        directory=str(barrier_dir), marker_sha256=sha, timeout_seconds=30
    )
    # A：matched 走到发布路径；skin 结果图置空以越过归档、直达发布/完成围栏。
    face_a = FaceDouble(search="matched", face_subject_ref=ref, barrier=barrier)
    skin_a = SkinDouble(result_images=[])
    claim_a = next(
        c
        for c in claim_batch(engine, worker_id="A", lease_seconds=1, batch_size=1)
        if c.id == jid
    )
    ctx_a = make_ctx(
        engine, claim_a, extras={"storage": storage, "face_port": face_a, "skin_port": skin_a}
    )

    box: dict[str, Any] = {}

    def run_a() -> None:
        try:
            box["result"] = analyze_handler.handle(ctx_a, claim_a)
        except BaseException as exc:  # noqa: BLE001 - 失败时记录以便断言
            box["exc"] = exc

    thread_a = threading.Thread(target=run_a, daemon=True)
    thread_a.start()
    assert _wait_file(barrier_dir / "consumed", timeout=10)  # A 已算出旧结果并阻塞
    assert thread_a.is_alive()
    _evidence(
        "A_in_barrier",
        owner=claim_a.lease_owner,
        lease_revision=claim_a.lease_revision,
        attempt_count=claim_a.attempt_count,
        assessment=fetch_assessment(engine, aid)["status"],
    )

    # 短租约自然过期（未关闭续租机制：单次 handle 无续租线程）→ 真实回收
    time.sleep(1.2)
    assert recover_expired(engine) >= 1
    job_recovered = fetch_job(engine, jid)
    assert job_recovered["status"] == "queued" and job_recovered["lease_owner"] is None
    rev_recovered = int(job_recovered["lease_revision"])
    assert rev_recovered == int(claim_a.lease_revision) + 1  # 回收推进围栏令牌
    _evidence(
        "after_recover_expired",
        status=job_recovered["status"],
        lease_owner=job_recovered["lease_owner"],
        lease_revision=rev_recovered,
    )

    # 接管者 B：quality=needs_retake（barrier 已被 A 消费 → B 不阻塞）→ 原子提交 needs_retake
    face_b = FaceDouble(quality="needs_retake", barrier=barrier)
    claim_b = next(
        c
        for c in claim_batch(engine, worker_id="B", lease_seconds=60, batch_size=1)
        if c.id == jid
    )
    assert int(claim_b.lease_revision) == rev_recovered + 1
    _evidence(
        "B_takeover",
        owner=claim_b.lease_owner,
        lease_revision=claim_b.lease_revision,
        attempt_count=claim_b.attempt_count,
    )
    ctx_b = make_ctx(engine, claim_b, extras={"storage": storage, "face_port": face_b})
    result_b = analyze_handler.handle(ctx_b, claim_b)
    assert result_b is not None
    complete_success(engine, claim_b, handler_result_tx=result_b.business_tx)
    job_b = fetch_job(engine, jid)
    assert job_b["status"] == "succeeded" and job_b["lease_owner"] == "B"
    assert int(job_b["attempt_count"]) == 2
    assert fetch_assessment(engine, aid)["status"] == "needs_retake"
    _evidence(
        "B_committed",
        job_status=job_b["status"],
        attempt_count=job_b["attempt_count"],
        assessment=fetch_assessment(engine, aid)["status"],
    )

    # 释放原旧 provider：A 拿到入 barrier 前算好的旧结果（accepted），继续走发布/完成
    (barrier_dir / "released").write_text("go", encoding="utf-8")
    thread_a.join(timeout=10)
    assert not thread_a.is_alive()
    assert "exc" not in box, box.get("exc")
    result_a = box.get("result")
    assert result_a is not None
    _evidence("A_released_old_result", result_type=type(result_a).__name__)

    # 旧执行提交 → 既有租约围栏拒绝（lease_revision/status 已变），业务写整体回滚
    with pytest.raises(StaleGeneration):
        complete_success(engine, claim_a, handler_result_tx=result_a.business_tx)
    _evidence("A_fenced", outcome="StaleGeneration")

    final = fetch_assessment(engine, aid)
    assert final["status"] == "needs_retake"  # 旧结果未覆盖新版本/新状态
    assert final["report_id"] is None and final["report_payload"] is None
    assert final["member_id"] is None  # 接管者 needs_retake 未被旧执行改写
    with engine.connect() as conn:
        ready = conn.execute(
            text(
                "SELECT count(*) FROM skin_assessments WHERE id = CAST(:a AS uuid)"
                " AND status = 'report_ready'"
            ),
            {"a": aid},
        ).scalar_one()
    assert int(ready) == 0
    # barrier 自清理：无残留 sentinel
    assert not (barrier_dir / "consumed").exists()
    assert not (barrier_dir / "released").exists()


def test_late_barrier_env_factory_first_call_blocks_then_returns_old_result(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """env 工厂装配 ⑦：首个命中标记调用阻塞，释放后返回**入 barrier 前**的旧结果。"""
    marker = b"factory-" + uuid.uuid4().bytes
    barrier_dir = tmp_path / "fb"
    monkeypatch.setenv("MVP_D_DOUBLE_LATE_BARRIER", "true")
    monkeypatch.setenv("MVP_D_DOUBLE_LATE_BARRIER_DIR", str(barrier_dir))
    monkeypatch.setenv("MVP_D_DOUBLE_LATE_BARRIER_SHA256", hashlib.sha256(marker).hexdigest())
    monkeypatch.setenv("MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS", "10")

    port = build_face_port(DConfig.from_env(), environment="dev")
    out: dict[str, Any] = {}
    worker = threading.Thread(
        target=lambda: out.__setitem__("r", port.quality({"front": marker})), daemon=True
    )
    worker.start()
    assert _wait_file(barrier_dir / "consumed", timeout=5)
    assert worker.is_alive()  # 确实被阻塞
    (barrier_dir / "released").write_text("go", encoding="utf-8")
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert out["r"].status == "accepted"  # 先算后等：旧结果原样返回（非重算）
    assert not (barrier_dir / "consumed").exists()
    assert not (barrier_dir / "released").exists()


def test_late_barrier_is_one_shot_takeover_not_blocked(tmp_path: Any) -> None:
    """一次性：首次命中阻塞；期间第二次命中（接管者）立即返回、不被阻塞。"""
    marker = b"oneshot-" + uuid.uuid4().bytes
    barrier_dir = tmp_path / "ob"
    barrier = LateReturnBarrier(
        directory=str(barrier_dir),
        marker_sha256=hashlib.sha256(marker).hexdigest(),
        timeout_seconds=10,
    )
    holder: dict[str, Any] = {}
    first = threading.Thread(
        target=lambda: holder.__setitem__(
            "r", barrier.compute_then_wait({"front": marker}, "old")
        ),
        daemon=True,
    )
    first.start()
    assert _wait_file(barrier_dir / "consumed", timeout=5)
    assert barrier.compute_then_wait({"front": marker}, "takeover") == "takeover"
    (barrier_dir / "released").write_text("go", encoding="utf-8")
    first.join(timeout=5)
    assert holder["r"] == "old"


def test_late_barrier_timeout_cleans_and_raises(tmp_path: Any) -> None:
    """有界：超时清理 sentinel 并抛既有 ProviderUnavailable（可重试路径），不留残留。"""
    marker = b"timeout-" + uuid.uuid4().bytes
    barrier_dir = tmp_path / "tb"
    barrier = LateReturnBarrier(
        directory=str(barrier_dir),
        marker_sha256=hashlib.sha256(marker).hexdigest(),
        timeout_seconds=1,
    )
    with pytest.raises(ProviderUnavailable):
        barrier.compute_then_wait({"front": marker}, "old")
    assert not (barrier_dir / "consumed").exists()
    assert not (barrier_dir / "released").exists()


# ===================================================== 项 B：SC-02-10 确定性终态失败


@pytest.mark.parametrize("mode", ["unknown_metric", "out_of_range", "bad_unit"])
def test_sc0210_skin_invalid_reaches_existing_terminal_failure(
    engine: Engine, tmp_path: Any, monkeypatch: Any, mode: str
) -> None:
    """skin 替身返回违约指标 → 既有 PROVIDER_CONTRACT_VIOLATION 终态，1 轮确定性到达。"""
    monkeypatch.setenv("MVP_D_SKIN_DOUBLE_INVALID", mode)
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(
        engine, status="queued", current_photo_version=1, processing_revision=2
    )
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    jid = _enqueue_analyze(engine, aid, 2, max_attempts=5)

    status, exc, _claim = run_claimed(engine, analyze_handler, jid, extras={"storage": storage})
    assert status == "failed" and exc is not None
    assert exc.code == "PROVIDER_CONTRACT_VIOLATION" and exc.retryable is False

    job = fetch_job(engine, jid)
    assert job["status"] == "failed"
    assert int(job["attempt_count"]) == 1  # 1 轮确定性终态，不依赖 attempt 预算耗尽

    a = fetch_assessment(engine, aid)
    assert a["status"] == "failed"
    assert a["failure_code"] == "PROVIDER_CONTRACT_VIOLATION"
    assert a["failure_detail"] and a["failure_detail"].get("reason")
    assert a["report_id"] is None and a["report_payload"] is None
    _evidence(
        "SC02-10_terminal",
        mode=mode,
        t05_status=a["status"],
        failure_code=a["failure_code"],
        failure_detail_reason=str(a["failure_detail"].get("reason"))[:80],
        job_status=job["status"],
        attempt_count=job["attempt_count"],
        retryable=exc.retryable,
    )

    # 无伪 report_ready；失败路径不产生后继任务（无 identity.enroll / plan.generate）
    with engine.connect() as conn:
        jobs = conn.execute(
            text("SELECT count(*) FROM async_jobs WHERE owner_id = CAST(:a AS uuid)"),
            {"a": aid},
        ).scalar_one()
        ready = conn.execute(
            text(
                "SELECT count(*) FROM skin_assessments WHERE id = CAST(:a AS uuid)"
                " AND status = 'report_ready'"
            ),
            {"a": aid},
        ).scalar_one()
    assert int(jobs) == 1
    assert int(ready) == 0


def test_skin_invalid_default_off_regression(engine: Engine, tmp_path: Any) -> None:
    """默认关闭：不设旋钮时既有发布路径正常（行为与现状一致）。"""
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(
        engine, status="queued", current_photo_version=1, processing_revision=2
    )
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    ref = str(uuid.uuid4())
    seed_member(engine, ns=DEFAULT_NS, ref=ref, assessment_id=aid)
    jid = _enqueue_analyze(engine, aid, 2, max_attempts=5)

    status, exc, _ = run_claimed(
        engine,
        analyze_handler,
        jid,
        extras={"storage": storage, "face_port": FaceDouble(search="matched", face_subject_ref=ref)},
    )
    assert status == "succeeded" and exc is None
    assert fetch_assessment(engine, aid)["status"] == "report_ready"


# ===================================================== 新旋钮守卫 / fail fast


@pytest.mark.parametrize(
    "name,value",
    [
        ("MVP_D_SKIN_DOUBLE_INVALID", "bogus"),
        ("MVP_D_DOUBLE_LATE_BARRIER", "bogus"),
    ],
)
def test_new_knob_invalid_value_fails_fast(
    monkeypatch: Any, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ProviderConfigError) as ei:
        DConfig.from_env()
    assert name in str(ei.value)


def test_barrier_enabled_requires_valid_sha_and_timeout(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_DOUBLE_LATE_BARRIER", "true")
    with pytest.raises(ProviderConfigError):
        DConfig.from_env()  # 缺 sha
    monkeypatch.setenv("MVP_D_DOUBLE_LATE_BARRIER_SHA256", "z" * 64)
    with pytest.raises(ProviderConfigError):
        DConfig.from_env()  # 非 hex
    monkeypatch.setenv("MVP_D_DOUBLE_LATE_BARRIER_SHA256", "a" * 64)
    monkeypatch.setenv("MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS", "0")
    with pytest.raises(ProviderConfigError):
        DConfig.from_env()  # timeout < 1


def test_new_knobs_covered_by_production_guard(monkeypatch: Any) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MVP_D_DOUBLE_LATE_BARRIER", "true")
    monkeypatch.setenv("MVP_D_DOUBLE_LATE_BARRIER_SHA256", "a" * 64)
    overrides = double_injection_overrides()
    assert "MVP_D_DOUBLE_LATE_BARRIER" in overrides
    with pytest.raises(ProviderConfigError):
        assert_no_double_injection_in_production()

    monkeypatch.delenv("MVP_D_DOUBLE_LATE_BARRIER")
    monkeypatch.delenv("MVP_D_DOUBLE_LATE_BARRIER_SHA256")
    monkeypatch.setenv("MVP_D_SKIN_DOUBLE_INVALID", "unknown_metric")
    assert "MVP_D_SKIN_DOUBLE_INVALID" in double_injection_overrides()
    with pytest.raises(ProviderConfigError):
        assert_no_double_injection_in_production()
