# -*- coding: utf-8 -*-
"""D/C Worker 替身 env 注入缝（E 6 项 ``seam_pending`` 的 Python 侧）定向测试。

约定（与 E 的隔离设计一致）：
- 全部旋钮**默认关闭**且只被 double 分支读取；通过进程 env 注入，逐测试隔离；
- 生产 fail-closed：生产信号（含混合 profile / 矛盾 env）出现注入开关即拒绝启动；
- **不改**业务判定：只改替身返回的外部结果，业务分支原样执行。

真实 PG @55435/``mvp_b_dev``（经 conftest 临时库）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from conftest import enqueue, fetch_job
from d_support import (
    DEFAULT_NS,
    clean_d_tables,
    count_members,
    fetch_assessment,
    fetch_job_full_by_id,
    fetch_plan,
    fetch_result_media,
    mark_report_ready,
    photo_versions_for,
    run_claimed,
    seed_assessment,
    seed_member,
    seed_microcrystal,
    seed_plan,
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
    build_face_port,
)
from mvp_worker.handlers.plan_generate import handler as plan_handler
from mvp_worker.media.storage import (
    STORAGE_DOUBLE_FAIL_PUT_ENV,
    FilesystemStorageDouble,
    StorageError,
)

# 本批注入开关（默认关闭）；autouse 清空保证测试实例/RUN_ID 间不串扰。
_INJECTION_ENVS = (
    "MVP_D_FACE_DOUBLE_QUALITY",
    "MVP_D_FACE_DOUBLE_REQUIRED_VIEWS",
    "MVP_D_FACE_DOUBLE_SAME_PERSON",
    "MVP_D_FACE_DOUBLE_SEARCH",
    "MVP_D_PLAN_DOUBLE_MODE",
    "MVP_D_SKIN_DOUBLE_HOLD",
    STORAGE_DOUBLE_FAIL_PUT_ENV,
)


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


@pytest.fixture(autouse=True)
def _default_injection_off(monkeypatch: Any) -> None:
    """每个测试从"默认关闭"起步（env 进程隔离，不跨测试泄漏）。"""
    for name in _INJECTION_ENVS:
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


def _seed_analysis_case(
    engine: Engine, tmp_path: Any, *, rev: int = 2, status: str = "queued"
) -> tuple[FilesystemStorageDouble, str, dict[str, str]]:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(
        engine, status=status, current_photo_version=1, processing_revision=rev
    )
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    return storage, aid, images


def _enqueue_analyze(
    engine: Engine, aid: str, rev: int, *, max_attempts: int = 5
) -> str:
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


def _seed_plan_case(engine: Engine, tmp_path: Any) -> tuple[Any, str, str, str]:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(engine, status="queued", current_photo_version=1, processing_revision=1)
    member = seed_member(engine, ns=DEFAULT_NS, ref=str(uuid.uuid4()), assessment_id=aid)
    mark_report_ready(engine, aid, member_id=member, report_photo_version=1)
    pid = seed_plan(
        engine,
        assessment_id=aid,
        member_id=member,
        generation_status="waiting_inputs",
        input_photo_version=1,
        generation_revision=0,
    )
    seed_microcrystal(engine)  # 能力就绪 → 不 defer，直达 port.generate
    return storage, aid, member, pid


def _enqueue_plan(engine: Engine, pid: str, rev: int, *, max_attempts: int = 5) -> str:
    jid, _ = enqueue(
        engine,
        job_type="plan.generate",
        dedup_key=f"plan:{pid}:{rev}",
        owner_type="plan",
        owner_id=pid,
        input_revision=rev,
        payload={"schema_version": 1, "plan_id": pid, "generation_revision": str(rev)},
        max_attempts=max_attempts,
    )
    return jid


# ================================================================ 1) 质量缝


def test_face_quality_needs_retake_env_seam(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """SC-02-05/08/09：quality=needs_retake → 需补拍视角、不产生报告。"""
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_QUALITY", "needs_retake")
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_REQUIRED_VIEWS", "front,right")
    storage, aid, _ = _seed_analysis_case(engine, tmp_path)
    jid = _enqueue_analyze(engine, aid, 2)

    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras={"storage": storage})
    assert status == "succeeded" and exc is None

    a = fetch_assessment(engine, aid)
    assert a["status"] == "needs_retake"  # E 断言：任务返回需补拍
    assert a["report_payload"] is None and a["report_id"] is None  # 不冒充报告就绪
    assert a["failure_code"] == "QUALITY_REJECTED"
    # Java 侧投影读取 required_views 的权威通道 = identity_result.quality
    assert a["identity_result"]["quality"] == {
        "status": "needs_retake",
        "required_views": ["front", "right"],
    }
    with engine.connect() as conn:
        ready = conn.execute(
            text(
                "SELECT count(*) FROM skin_assessments WHERE id = CAST(:id AS uuid)"
                " AND status = 'report_ready'"
            ),
            {"id": aid},
        ).scalar_one()
    assert int(ready) == 0


def test_face_quality_default_accepted_regression() -> None:
    """默认关闭回归：工厂未设旋钮时替身行为与旧 `FaceDouble()` 完全一致。

    真实 handler 默认路径（reliable_new/matched 全流程）由既有
    ``test_assessment_analyze.py`` 全套覆盖；此处锁定"新工厂透传默认值"这一新接线。
    """
    cfg = DConfig.from_env()
    assert (cfg.face_double_quality, cfg.face_double_search, cfg.face_double_same_person) == (
        "accepted",
        "reliable_new",
        True,
    )
    assert cfg.face_double_required_views == ()
    port = build_face_port(cfg, environment="dev")
    assert port.quality({}).status == "accepted"
    assert port.same_person({}).ok is True
    assert port.search_1n("ns", {}).classification == "reliable_new"


# ================================================================ 2) 身份缝


def test_same_person_false_never_enrolls(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """SC-02-06：same_person=false → NOT_SAME_PERSON；不误归成员/不自动建档/无报告。"""
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_SAME_PERSON", "false")
    storage, aid, _ = _seed_analysis_case(engine, tmp_path)
    members_before = count_members(engine)
    jid = _enqueue_analyze(engine, aid, 2)

    status, _exc, _ = run_claimed(engine, analyze_handler, jid, extras={"storage": storage})
    assert status == "succeeded"

    a = fetch_assessment(engine, aid)
    assert a["status"] == "needs_retake"
    assert a["failure_code"] == "NOT_SAME_PERSON"
    assert a["member_id"] is None
    assert a["report_payload"] is None
    assert count_members(engine) == members_before  # 不自动建档


@pytest.mark.parametrize("search", ["uncertain", "ambiguous"])
def test_search_uncertain_never_enrolls(
    engine: Engine, tmp_path: Any, monkeypatch: Any, search: str
) -> None:
    """SC-02-06：search=uncertain/ambiguous → IDENTITY_UNCERTAIN；同样不建档/无报告。"""
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_SEARCH", search)
    storage, aid, _ = _seed_analysis_case(engine, tmp_path)
    members_before = count_members(engine)
    jid = _enqueue_analyze(engine, aid, 2)

    status, _exc, _ = run_claimed(engine, analyze_handler, jid, extras={"storage": storage})
    assert status == "succeeded"

    a = fetch_assessment(engine, aid)
    assert a["status"] == "needs_retake"
    assert a["failure_code"] == "IDENTITY_UNCERTAIN"
    assert a["member_id"] is None and a["report_payload"] is None
    assert count_members(engine) == members_before


def test_search_matched_env_value_builds_matched_double(monkeypatch: Any) -> None:
    """search=matched 旋钮值域可用（工厂透传替身既有参数）。"""
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_SEARCH", "matched")
    cfg = DConfig.from_env()
    assert cfg.face_double_search == "matched"
    port = build_face_port(cfg, environment="dev")
    assert port.search_1n("ns", {"front": b"x"}).classification == "matched"


def test_search_matched_publishes_existing_member(engine: Engine, tmp_path: Any) -> None:
    """「可靠匹配已有成员」分支可用（既有成员被正确关联，不新建）。"""
    storage, aid, _ = _seed_analysis_case(engine, tmp_path)
    ref = str(uuid.uuid4())
    member = seed_member(engine, ns=DEFAULT_NS, ref=ref, assessment_id=aid)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="matched", face_subject_ref=ref)

    status, _exc, _ = run_claimed(
        engine, analyze_handler, jid, extras={"storage": storage, "face_port": face}
    )
    assert status == "succeeded"
    a = fetch_assessment(engine, aid)
    assert a["status"] == "report_ready"
    assert str(a["member_id"]) == member
    assert a["identity_result"]["classification"] == "matched"


# ================================================================ 3) 方案缝


def test_plan_timeout_retryable_then_terminal_deterministic(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """SC-03-07：timeout 确定性可重试→终态；绝不 ready；last_error 结构符合既有语义。"""
    monkeypatch.setenv("MVP_D_PLAN_DOUBLE_MODE", "timeout")
    storage, _aid, _member, pid = _seed_plan_case(engine, tmp_path)
    jid = _enqueue_plan(engine, pid, 0, max_attempts=2)

    # attempt 1 → 可重试
    status, exc, _ = run_claimed(engine, plan_handler, jid, extras={"storage": storage})
    assert status == "failed" and exc is not None
    assert exc.code == "DEPENDENCY_UNAVAILABLE" and exc.retryable is True
    assert fetch_plan(engine, pid)["generation_status"] != "ready"
    assert fetch_plan(engine, pid)["plan_payload"] is None
    job1 = fetch_job_full_by_id(engine, jid)
    assert job1["status"] == "queued" and int(job1["attempt_count"]) == 1
    err1 = job1["last_error"]  # jsonb 列 → psycopg 已解析为 dict
    assert err1["code"] == "DEPENDENCY_UNAVAILABLE" and err1["retryable"] is True
    assert "retry_after_seconds" in err1  # 既有退避语义

    # attempt 2（预算耗尽）→ 终态
    status2, exc2, _ = run_claimed(engine, plan_handler, jid, extras={"storage": storage})
    assert status2 == "failed" and exc2 is not None
    assert exc2.code == "DEPENDENCY_UNAVAILABLE" and exc2.retryable is False
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] == "failed"  # 终态，绝不 ready
    assert plan["plan_payload"] is None and plan["target_count"] is None
    assert plan["failure_detail"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert fetch_job(engine, jid)["status"] == "failed"


def test_plan_mode_valid_recovery_to_ready(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """关闭注入（默认 valid）后同一路径可正常生成 → 证明可恢复、无脏终态。"""
    storage, _aid, _member, pid = _seed_plan_case(engine, tmp_path)
    jid = _enqueue_plan(engine, pid, 0, max_attempts=3)
    status, exc, _ = run_claimed(engine, plan_handler, jid, extras={"storage": storage})
    assert status == "succeeded" and exc is None
    assert fetch_plan(engine, pid)["generation_status"] == "ready"


@pytest.mark.parametrize(
    "mode,expected_code,expected_retryable",
    [
        ("failure", "DEPENDENCY_UNAVAILABLE", True),
        ("n_zero", "PLAN_VALIDATION_FAILED", True),
        ("unknown_region", "PLAN_VALIDATION_FAILED", True),
    ],
)
def test_plan_failure_and_invalid_shapes_preserved(
    engine: Engine,
    tmp_path: Any,
    monkeypatch: Any,
    mode: str,
    expected_code: str,
    expected_retryable: bool,
) -> None:
    """failure / 既有非法形状经 env 选择后保持原失败语义（不新增错误码）。"""
    monkeypatch.setenv("MVP_D_PLAN_DOUBLE_MODE", mode)
    storage, _aid, _member, pid = _seed_plan_case(engine, tmp_path)
    jid = _enqueue_plan(engine, pid, 0, max_attempts=3)
    status, exc, _ = run_claimed(engine, plan_handler, jid, extras={"storage": storage})
    assert status == "failed" and exc is not None
    assert exc.code == expected_code and exc.retryable is expected_retryable
    plan = fetch_plan(engine, pid)
    assert plan["generation_status"] != "ready" and plan["plan_payload"] is None


# ============================================== SC-02-09 hold/release（进程级）


def test_sc0209_dedicated_hold_release_uses_existing_retryable_semantics(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """旧分析「hold/release」复用**既有** retryable 语义（`JobFailed(retryable=True)` 退避重排队）。

    进程级（端口无法按 task/photo 版本键控）：hold = `MVP_D_SKIN_DOUBLE_HOLD=true` →
    analyze 以可重试异常失败、旧 job 停在 queued；release = 撤销开关后同一 job 可继续。
    不 sleep、不改 DB、不改业务判定。
    """
    monkeypatch.setenv("MVP_D_SKIN_DOUBLE_HOLD", "true")  # hold（可重试，非终态）
    storage, aid, _ = _seed_analysis_case(engine, tmp_path, rev=1)
    jid = _enqueue_analyze(engine, aid, 1, max_attempts=5)

    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras={"storage": storage})
    assert status == "failed" and exc is not None
    assert exc.code == "DEPENDENCY_UNAVAILABLE" and exc.retryable is True
    a = fetch_assessment(engine, aid)
    assert a["status"] != "report_ready" and a["report_payload"] is None
    assert fetch_job(engine, jid)["status"] == "queued"  # 持有中、可释放

    # release：撤销 hold，同一 job 继续（不再以 DEPENDENCY_UNAVAILABLE 失败）
    monkeypatch.delenv("MVP_D_SKIN_DOUBLE_HOLD")
    status2, exc2, _ = run_claimed(engine, analyze_handler, jid, extras={"storage": storage})
    assert exc2 is None or exc2.code != "DEPENDENCY_UNAVAILABLE"


def test_sc0209_old_revision_released_does_not_overwrite_new_report(
    engine: Engine, tmp_path: Any
) -> None:
    """新版本成功发布后释放旧执行：既有 processing_revision 守卫使旧结果不覆盖新值。"""
    storage, aid, _ = _seed_analysis_case(engine, tmp_path, rev=2, status="analyzing")
    member = seed_member(engine, ns=DEFAULT_NS, ref=str(uuid.uuid4()), assessment_id=aid)
    rid = mark_report_ready(engine, aid, member_id=member, report_photo_version=2)
    before = fetch_assessment(engine, aid)

    # 旧代次执行（rev=1）迟到释放
    jid = _enqueue_analyze(engine, aid, 1, max_attempts=3)
    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras={"storage": storage})
    assert status == "succeeded" and exc is None

    after = fetch_assessment(engine, aid)
    assert after["status"] == "report_ready"
    assert str(after["report_id"]) == str(before["report_id"]) == str(rid)
    assert after["report_photo_version"] == 2  # 新版本保持
    assert after["report_payload"] == before["report_payload"]  # 旧结果未覆盖


# ================================================================ 4) 存储缝


def test_storage_fail_put_is_result_purpose_scoped(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """结果图保存失败与 Java 侧上传**按用途可区分**：只失败 assessment_result。"""
    monkeypatch.setenv(STORAGE_DOUBLE_FAIL_PUT_ENV, "true")
    storage = FilesystemStorageDouble(tmp_path / "storage")
    with pytest.raises(StorageError):
        storage.put("dev/assessment_result/m1", b"x")
    storage.put("dev/assessment_source/m1", b"x")  # 源图用途不受影响
    assert storage.exists("dev/assessment_source/m1")


def test_storage_fail_put_result_archive_retryable_then_recovery(
    engine: Engine, tmp_path: Any, monkeypatch: Any
) -> None:
    """SC-C-05：结果图保存失败 → 既有 RESULT_ARCHIVE_FAILED（可重试）、不伪报成功；
    关闭注入后重跑成功（无脏成功、可恢复）。"""
    storage, aid, _ = _seed_analysis_case(engine, tmp_path)
    ref = str(uuid.uuid4())
    member = seed_member(engine, ns=DEFAULT_NS, ref=ref, assessment_id=aid)
    # 用 matched 身份分支：单次 analyze 即可到达结果图归档（聚焦存储缝）。
    extras = {
        "storage": storage,
        "face_port": FaceDouble(search="matched", face_subject_ref=ref),
    }
    jid = _enqueue_analyze(engine, aid, 2)
    monkeypatch.setenv(STORAGE_DOUBLE_FAIL_PUT_ENV, "true")

    status, exc, _ = run_claimed(engine, analyze_handler, jid, extras=extras)
    assert status == "failed" and exc is not None
    assert exc.code == "RESULT_ARCHIVE_FAILED" and exc.retryable is True
    a = fetch_assessment(engine, aid)
    assert a["status"] != "report_ready"
    assert a["report_payload"] is None and a["report_id"] is None
    # 不得出现"已可用但对象缺失"的脏行：失败时结果图行仍是 pending
    assert all(r["state"] != "available" for r in fetch_result_media(engine, aid, 1))
    assert fetch_job(engine, jid)["status"] == "queued"

    monkeypatch.delenv(STORAGE_DOUBLE_FAIL_PUT_ENV)
    status2, exc2, _ = run_claimed(engine, analyze_handler, jid, extras=extras)
    assert status2 == "succeeded" and exc2 is None
    a2 = fetch_assessment(engine, aid)
    assert a2["status"] == "report_ready" and a2["report_payload"] is not None
    assert str(a2["member_id"]) == member
    assert all(r["state"] == "available" for r in fetch_result_media(engine, aid, 1))


# ================================================================ 5) 配置守卫


@pytest.mark.parametrize(
    "name,value",
    [
        ("MVP_D_FACE_DOUBLE_QUALITY", "bogus"),
        ("MVP_D_FACE_DOUBLE_SEARCH", "bogus"),
        ("MVP_D_PLAN_DOUBLE_MODE", "bogus"),
        ("MVP_D_FACE_DOUBLE_REQUIRED_VIEWS", "eye"),
    ],
)
def test_invalid_injection_value_fails_fast(
    monkeypatch: Any, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ProviderConfigError):
        DConfig.from_env()


@pytest.mark.parametrize(
    "prod_env",
    [
        {"APP_ENV": "production"},
        {"MVP_WORKER_ENVIRONMENT": "production"},
        {"MVP_NOTIFY_ENV": "prod"},
        # 混合 profile：app.env=dev 被 prod profile 覆盖 → 仍视为生产
        {"APP_ENV": "dev", "SPRING_PROFILES_ACTIVE": "prod,dev"},
        # 矛盾组合：高优先级 MVP_NOTIFY_ENV=dev 掩盖 APP_ENV=production → 仍拒绝
        {"MVP_NOTIFY_ENV": "dev", "APP_ENV": "production"},
    ],
)
def test_production_with_injection_refused_at_load(
    monkeypatch: Any, prod_env: dict[str, str]
) -> None:
    for key, value in prod_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MVP_D_FACE_DOUBLE_QUALITY", "needs_retake")
    assert double_injection_overrides()  # 确有非默认注入
    with pytest.raises(ProviderConfigError):
        assert_no_double_injection_in_production()


def test_production_refuses_hold_switch(monkeypatch: Any) -> None:
    """hold 开关也纳入生产 fail-closed（不是可绕过项）。"""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MVP_D_SKIN_DOUBLE_HOLD", "true")
    assert double_injection_overrides() == {"MVP_D_SKIN_DOUBLE_HOLD": "true"}
    with pytest.raises(ProviderConfigError):
        assert_no_double_injection_in_production()


def test_production_with_defaults_keeps_existing_behavior(monkeypatch: Any) -> None:
    """production + 全默认：本批守卫不触发；既有 provider-double 拒绝不变。"""
    monkeypatch.setenv("APP_ENV", "production")
    assert double_injection_overrides() == {}
    assert_no_double_injection_in_production()  # 不抛
    from mvp_worker.handlers.dshared.providers import build_face_port

    with pytest.raises(ProviderConfigError):  # 既有 _forbid_double_in_production
        build_face_port(DConfig.from_env(), environment="production")


def test_startup_refuses_production_with_injection_via_cli() -> None:
    """真实启动入口：production + 注入 → 进程非 0 退出（早于 DB/健康端口）。"""
    env = dict(os.environ)
    env.update(
        {
            "APP_ENV": "production",
            "MVP_D_FACE_DOUBLE_QUALITY": "needs_retake",
        }
    )
    env.pop("MVP_NOTIFY_ENV", None)
    env.pop("MVP_WORKER_ENVIRONMENT", None)
    proc = subprocess.run(
        [sys.executable, "-m", "mvp_worker", "--check"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "production fail-closed" in combined
    assert "MVP_D_FACE_DOUBLE_QUALITY" in combined


def test_injection_switches_default_off_and_env_scoped() -> None:
    """默认关闭 + 进程 env 隔离（autouse 清空，无跨实例/RUN_ID 残留）。"""
    assert double_injection_overrides() == {}
    assert DConfig.from_env().face_double_quality == "accepted"
    if STORAGE_DOUBLE_FAIL_PUT_ENV in os.environ:
        assert os.environ[STORAGE_DOUBLE_FAIL_PUT_ENV] in ("", "0", "false", "no", "off")
