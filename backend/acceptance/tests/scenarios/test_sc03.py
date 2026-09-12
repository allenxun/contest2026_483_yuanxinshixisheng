# -*- coding: utf-8 -*-
"""SC-03 · 报告、方案生成与两端视图 —— 集成轮 batch 2 lane A2（9 节点）。

真实链：云台会话 → M3-A01 受理 → worker `--once`（analyze/enroll/plan.generate）→
T05 报告 → T06 方案；B M2-A04/A05 能力观察真实端点；APP 授权后 M3-A04/A05、M4-A01/A02。
不可注入子形态（如 plan 超时）按 lane A1 先例结算 pending+精确披露，不伪造 pass。
"""
from __future__ import annotations

import json
import uuid

import pytest

from framework import gate
from framework import live
from driver import infra as I
from driver import c_care as CC


def _mark(sid, prio, scope, pkgs, deps):
    def deco(fn):
        fn = pytest.mark.sc_id(sid)(fn)
        fn = pytest.mark.priority(prio)(fn)
        fn = pytest.mark.scope(scope)(fn)
        for p in pkgs:
            fn = pytest.mark.package(p)(fn)
        for d in deps:
            fn = pytest.mark.deps(d)(fn)
        return fn
    return deco


def _rec(se, method, path, code, body, req=None, headers=None):
    se.record_raw(method=method, path=path, status=code, request_id="",
                  request_headers=headers or {}, request_json=req,
                  response_excerpt=json.dumps(body, ensure_ascii=False)[:4000],
                  started_at=0.0, elapsed_ms=0.0)


def _audit(se, note, code=0, body=None):
    se.record_raw(method="AUDIT", path=note, status=code, request_headers={}, request_json=None,
                  response_excerpt=json.dumps(body or {}, ensure_ascii=False)[:800],
                  started_at=0.0, elapsed_ms=0.0)


def _decl(se):
    se.doubles.add("face_algo", "double", "D FaceDouble")
    se.doubles.add("skin_algo", "double", "D SkinDouble")
    se.doubles.add("llm_plan", "double", "D PlanDouble")
    se.doubles.add("oss", "double", "A FilesystemStorageDouble")
    se.doubles.add("gimbal_device", "double", "云台会话 dev 凭据")


def _worker_until(sql_cond, cycles=140, env_extra=None):
    for _ in range(cycles):
        if CC.scalar(sql_cond) == "1":
            return True
        I.worker_once(env_extra=env_extra, timeout=180)
    return CC.scalar(sql_cond) == "1"


def _ready(se, *, obs=None):
    """跑通真实链到 report_ready，返回上下文（含 mid/rid/planId）。"""
    g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    ready = _worker_until(f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{tid}'")
    mid = CC.scalar(f"SELECT member_id::text FROM skin_assessments WHERE id='{tid}'")
    rid = CC.scalar(f"SELECT report_id::text FROM skin_assessments WHERE id='{tid}'")
    plan = CC.scalar(f"SELECT id::text FROM care_plans WHERE assessment_id='{tid}'")
    assert c == 202 and ready and mid and rid, (c, ready, mid, rid)
    return {"g": g, "tok": tok, "tid": tid, "mid": mid, "rid": rid, "plan": plan}


@_mark("SC-03-01", "P0", "后端", ["D"], ["D01"])
def test_SC_03_01(scenario_evidence):
    """报告列表/详情成员隔离：仅可访问成员报告；越权统一 404 不泄存在性。"""
    se = scenario_evidence
    _decl(se)
    ctx = _ready(se)
    a = live.app_login("sc0301a")
    b = live.app_login("sc0301b")
    CC.seed_grant(a["accountId"], ctx["mid"], status="active")
    c1, b1, _ = I.http("GET", f"/api/v1/members/{ctx['mid']}/skin-reports", token=a["access"])
    _rec(se, "GET", f"/api/v1/members/{ctx['mid']}/skin-reports", c1, b1)
    c2, b2, _ = I.http("GET", f"/api/v1/skin-reports/{ctx['rid']}", token=a["access"])
    _rec(se, "GET", f"/api/v1/skin-reports/{ctx['rid']}", c2, b2)
    c3, b3, _ = I.http("GET", f"/api/v1/members/{ctx['mid']}/skin-reports", token=b["access"])
    _rec(se, "GET", f"/api/v1/members/{ctx['mid']}/skin-reports", c3, b3)
    c4, b4, _ = I.http("GET", f"/api/v1/skin-reports/{ctx['rid']}", token=b["access"])
    _rec(se, "GET", f"/api/v1/skin-reports/{ctx['rid']}", c4, b4)
    assert c1 == 200 and any(it.get("reportId") == ctx["rid"]
                             for it in ((b1.get("data") or {}).get("items") or []))
    assert c2 == 200
    assert c3 == 404 and b3["error"]["code"] == "RESOURCE_NOT_VISIBLE"
    assert c4 == 404 and b4["error"]["code"] == "RESOURCE_NOT_VISIBLE"
    se.seal()


@_mark("SC-03-02", "P0", "后端", ["D"], ["D01"])
def test_SC_03_02(scenario_evidence):
    """APP 完整版 vs 云台简版：APP 按授权查 full；云台仅 brief，传 full 被拒。"""
    se = scenario_evidence
    _decl(se)
    ctx = _ready(se)
    a = live.app_login("sc0302")
    CC.seed_grant(a["accountId"], ctx["mid"], status="active")
    ca, ba, _ = I.http("GET", f"/api/v1/skin-reports/{ctx['rid']}", token=a["access"])
    _rec(se, "GET", f"/api/v1/skin-reports/{ctx['rid']}", ca, ba, req={"view": "default-full"})
    cg, bg, _ = I.http("GET", f"/api/v1/skin-reports/{ctx['rid']}", token=ctx["tok"])
    _rec(se, "GET", f"/api/v1/skin-reports/{ctx['rid']}", cg, bg, req={"caller": "gimbal-brief"})
    cf, bf, _ = I.http("GET", f"/api/v1/skin-reports/{ctx['rid']}?view=full", token=ctx["tok"])
    _rec(se, "GET", f"/api/v1/skin-reports/{ctx['rid']}?view=full", cf, bf, req={"caller": "gimbal-full"})
    assert ca == 200 and (ba.get("data") or {}).get("view") == "full"
    assert cg == 200 and (bg.get("data") or {}).get("view") == "brief"
    assert (bg.get("data") or {}).get("memberId") is None  # 简版不泄成员
    assert cf == 403 and bf["error"]["code"] == "CALLER_NOT_ALLOWED"
    se.seal()


@_mark("SC-03-03", "P1", "集成", ["D"], ["D07"])
def test_SC_03_03(scenario_evidence):
    """报告就绪但方案未完成：报告立即可查；方案明确 waiting_inputs 等待态，不阻塞报告。"""
    se = scenario_evidence
    _decl(se)
    ctx = _ready(se)
    a = live.app_login("sc0303")
    CC.seed_grant(a["accountId"], ctx["mid"], status="active")
    st = CC.scalar(f"SELECT generation_status FROM care_plans WHERE id='{ctx['plan']}'")
    cp, bp, _ = I.http("GET", f"/api/v1/care-plans/{ctx['plan']}?view=full", token=a["access"])
    _rec(se, "GET", f"/api/v1/care-plans/{ctx['plan']}?view=full", cp, bp)
    cr, br, _ = I.http("GET", f"/api/v1/skin-reports/{ctx['rid']}", token=a["access"])
    _rec(se, "GET", f"/api/v1/skin-reports/{ctx['rid']}", cr, br)
    data = bp.get("data") or {}
    assert st == "waiting_inputs", st
    assert cp == 200 and data.get("generationStatus") == "waiting_inputs"
    assert data.get("waitingReason") == "waiting_inputs" and data.get("plan") is None
    assert cr == 200  # 报告不被方案阻塞
    se.seal()


@_mark("SC-03-04", "P1", "集成", ["B", "D"], ["D06", "D07"])
def test_SC_03_04(scenario_evidence):
    """能力未齐等待 → 真实 B M2-A04 观察合法补齐 → plan.generate ready；重复同版本不重生成。"""
    se = scenario_evidence
    _decl(se)
    ctx = _ready(se)
    assert CC.scalar(f"SELECT generation_status FROM care_plans WHERE id='{ctx['plan']}'") == "waiting_inputs"
    a = live.app_login("sc0304")
    serial = f"mc-{uuid.uuid4().hex[:8]}"
    co, bo, _ = live.observe_microcrystal(a, serial, live.CAP_BASELINE)
    _rec(se, "POST", "/api/v1/microcrystal-observations", co, bo, req={"serial": serial, "cap": "baseline"})
    ok = _worker_until(f"SELECT (generation_status='ready')::int FROM care_plans WHERE id='{ctx['plan']}'")
    gen_rev = CC.scalar(f"SELECT generation_revision FROM care_plans WHERE id='{ctx['plan']}'")
    jobs = CC.scalar("SELECT count(*) FROM async_jobs WHERE job_type='plan.generate'")
    # 同能力版本重复上报 → 不重复生成
    co2, bo2, _ = live.observe_microcrystal(a, serial, live.CAP_BASELINE)
    _rec(se, "POST", "/api/v1/microcrystal-observations", co2, bo2, req={"serial": serial, "repeat": True})
    for _ in range(4):
        I.worker_once(timeout=180)
    gen_rev2 = CC.scalar(f"SELECT generation_revision FROM care_plans WHERE id='{ctx['plan']}'")
    jobs2 = CC.scalar("SELECT count(*) FROM async_jobs WHERE job_type='plan.generate'")
    assert co == 200 and ok, (co, bo)
    assert CC.scalar(f"SELECT generation_status FROM care_plans WHERE id='{ctx['plan']}'") == "ready"
    assert gen_rev == gen_rev2 and jobs == jobs2
    se.seal()


@_mark("SC-03-05", "P0", "后端", ["B"], ["D01", "D06"])
def test_SC_03_05(scenario_evidence):
    """能力登记不篡改归属/占用：合法观察被接收；伪造连接关系被拒，不抢占执行。"""
    se = scenario_evidence
    _decl(se)
    a = live.app_login("sc0305a")
    b = live.app_login("sc0305b")
    serial = f"mc-{uuid.uuid4().hex[:8]}"
    co, bo, _ = live.observe_microcrystal(a, serial, live.CAP_BASELINE)
    _rec(se, "POST", "/api/v1/microcrystal-observations", co, bo, req={"serial": serial, "valid": True})
    mid = CC.scalar(f"SELECT id::text FROM microcrystals WHERE serial_no='{serial}'")
    rev_before = CC.scalar(f"SELECT capabilities->>'revision' FROM microcrystals WHERE id='{mid}'")
    # 伪造：B 用他人 observerRef/account 的证明（签名对但主体不符）→ 403
    forged = live.connection_proof(serial, observer_type="app_account",
                                   observer_ref=f"{a['accountId']}:{a['installationId']}",
                                   account_id=a["accountId"], installation_id=a["installationId"])
    body = {"microcrystalSerial": serial, "connectionProof": forged,
            "capabilities": {"schemaVersion": 1, **{**live.CAP_BASELINE, "revision": 99}},
            "observationEpoch": f"obs-{uuid.uuid4().hex[:8]}", "observationSeq": "1",
            "observedAt": live.utcnow_iso(), "state": {"mode": "idle"}}
    cb, bb, _ = I.http("POST", "/api/v1/microcrystal-observations", token=b["access"], body=body,
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "POST", "/api/v1/microcrystal-observations", cb, bb, req={"serial": serial, "forged": True})
    rev_after = CC.scalar(f"SELECT capabilities->>'revision' FROM microcrystals WHERE id='{mid}'")
    executions = CC.scalar("SELECT count(*) FROM care_executions")
    assert co == 200
    assert cb == 403 and bb["error"]["code"] == "CALLER_NOT_ALLOWED"
    assert rev_before == rev_after and executions == "0"
    se.seal()


@_mark("SC-03-06", "P1", "后端", ["B"], ["D01", "D06"])
def test_SC_03_06(scenario_evidence):
    """读取已登记能力（M2-A05）：观察者可见含版本/更新时间；无关主体 404；不替代占用检查。"""
    se = scenario_evidence
    _decl(se)
    a = live.app_login("sc0306a")
    c = live.app_login("sc0306c")
    serial = f"mc-{uuid.uuid4().hex[:8]}"
    co, bo, _ = live.observe_microcrystal(a, serial, live.CAP_BASELINE)
    _rec(se, "POST", "/api/v1/microcrystal-observations", co, bo, req={"serial": serial})
    mid = CC.scalar(f"SELECT id::text FROM microcrystals WHERE serial_no='{serial}'")
    c1, b1, _ = live.get_capabilities(mid, a)
    _rec(se, "GET", f"/api/v1/microcrystals/{mid}/capabilities", c1, b1, req={"observer": "a"})
    c2, b2, _ = live.get_capabilities(mid, c)
    _rec(se, "GET", f"/api/v1/microcrystals/{mid}/capabilities", c2, b2, req={"observer": "unrelated"})
    executions = CC.scalar("SELECT count(*) FROM care_executions")
    data = b1.get("data") or {}
    assert co == 200 and c1 == 200
    assert str(data.get("capabilityRevision")) == "1"
    assert data.get("capabilities") and data.get("observedAt") is not None
    assert c2 == 404 and b2["error"]["code"] == "RESOURCE_NOT_VISIBLE"
    assert executions == "0"  # 读取不登记执行/不替代占用检查
    se.seal()


@_mark("SC-03-07", "P1", "集成", ["D"], ["D06", "D07"])
def test_SC_03_07(scenario_evidence):
    """大模型成功/失败/非法方案：正常成功已由 03-04 覆盖；本节点以受控配置 seam
    （baseline 缺 n_bounds/多项范围）验证非法/失败结果**不能变可执行方案**。
    超时子形态无注入 seam → 精确披露 pending。"""
    se = scenario_evidence
    _decl(se)
    g, tok = live.gimbal_with_token()
    malformed = {"MVP_PLAN_CAPABILITY_BASELINE": json.dumps({
        "schema_version": 1, "capability_id": "mvp-double-capability", "revision": 1,
        "parameter_ranges": {"intensity": {"unit": "percent", "min": 0.0, "max": 100.0}},
        "approved_regions": ["forehead", "left_cheek", "right_cheek", "nose"]})}
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    plan = ""
    st = ""
    for _ in range(30):
        plan = CC.scalar(f"SELECT id::text FROM care_plans WHERE assessment_id='{tid}'") or plan
        st = CC.scalar(f"SELECT generation_status FROM care_plans WHERE id='{plan}'") if plan else ""
        if st in ("failed", "ready"):
            break
        I.worker_once(env_extra=malformed, timeout=180)
    detail = CC.scalar(f"SELECT coalesce(failure_detail::text,'') FROM care_plans WHERE id='{plan}'") if plan else ""
    ready_rows = CC.scalar(f"SELECT count(*) FROM care_plans WHERE id='{plan}' AND generation_status='ready'") if plan else "0"
    _audit(se, "SC-03-07 malformed-baseline plan result", 0,
           {"status": st, "detail": detail[:120]})
    assert c == 202 and bool(plan) and st == "failed" and ready_rows == "0", (c, plan, st)
    assert "PLAN_SNAPSHOT_INVALID" in (detail or "")
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + "plan 超时子形态无注入 seam（D 未提供）；"
                "非法/失败结果已实测（PLAN_SNAPSHOT_INVALID），超时待 D seam 后补写")


@_mark("SC-03-08", "P0", "后端", ["C", "D"], ["D01"])
def test_SC_03_08(scenario_evidence):
    """APP 查有权方案 + 云台仅核验领取当前任务：云台不能历史列表/查方案；无按人脸找回端点。"""
    se = scenario_evidence
    _decl(se)
    ctx = _ready(se)
    a = live.app_login("sc0308")
    CC.seed_grant(a["accountId"], ctx["mid"], status="active")
    c1, b1, _ = I.http("GET", f"/api/v1/members/{ctx['mid']}/care-plans", token=a["access"])
    _rec(se, "GET", f"/api/v1/members/{ctx['mid']}/care-plans", c1, b1)
    c2, b2, _ = I.http("GET", f"/api/v1/care-plans/{ctx['plan']}?view=full", token=a["access"])
    _rec(se, "GET", f"/api/v1/care-plans/{ctx['plan']}?view=full", c2, b2)
    cg1, bg1, _ = I.http("GET", f"/api/v1/members/{ctx['mid']}/care-plans", token=ctx["tok"])
    _rec(se, "GET", f"/api/v1/members/{ctx['mid']}/care-plans", cg1, bg1, req={"caller": "gimbal"})
    cg2, bg2, _ = I.http("GET", f"/api/v1/care-plans/{ctx['plan']}", token=ctx["tok"])
    _rec(se, "GET", f"/api/v1/care-plans/{ctx['plan']}", cg2, bg2, req={"caller": "gimbal"})
    assert c1 == 200 and any(it.get("planId") == ctx["plan"]
                             for it in ((b1.get("data") or {}).get("items") or []))
    assert c2 == 200
    assert cg1 == 403 and bg1["error"]["code"] == "CALLER_NOT_ALLOWED"
    assert cg2 == 403 and bg2["error"]["code"] == "CALLER_NOT_ALLOWED"
    se.seal()


@_mark("SC-03-09", "P1", "后端", ["D"], [])
def test_SC_03_09(scenario_evidence):
    """报告/方案/任务重复查询零副作用：不生成新任务/不重分析/不重生成/不登记执行/不累计 K。"""
    se = scenario_evidence
    _decl(se)
    ctx = _ready(se)
    a = live.app_login("sc0309")
    CC.seed_grant(a["accountId"], ctx["mid"], status="active")
    def snap():
        return "|".join(CC.scalar(s) for s in (
            "SELECT count(*) FROM skin_assessments",
            "SELECT count(*) FROM async_jobs",
            "SELECT count(*) FROM care_executions",
            f"SELECT generation_revision FROM care_plans WHERE id='{ctx['plan']}'",
            f"SELECT coalesce(completed_count,0)||','||coalesce(progress_revision,0) FROM care_plans WHERE id='{ctx['plan']}'",
        ))
    before = snap()
    for _ in range(3):
        for path, token in ((f"/api/v1/members/{ctx['mid']}/skin-reports", a["access"]),
                            (f"/api/v1/skin-reports/{ctx['rid']}", a["access"]),
                            (f"/api/v1/care-plans/{ctx['plan']}?view=full", a["access"]),
                            (f"/api/v1/skin-assessment-tasks/{ctx['tid']}", ctx["tok"])):
            cc, bb, _ = I.http("GET", path, token=token)
            _rec(se, "GET", path, cc, bb, req={"repeat": True})
            assert cc == 200
    after = snap()
    _audit(se, "SC-03-09 zero-side-effect snapshot", 0, {"before": before, "after": after})
    assert before == after, (before, after)
    se.seal()
