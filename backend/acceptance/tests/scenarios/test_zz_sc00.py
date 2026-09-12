# -*- coding: utf-8 -*-
"""SC-00 · 完整业务流程 —— 集成轮 batch 2 lane C1（4 节点，全设备APP）。

端到端后端子步骤：云台 session→M3-A01→worker→T06 ready→APP 授权(M1)→C A03→A05→A08→A06
+控制端指针切换 T03；子步骤全验后结算 device_pending（真实联调待办）。
"""
from __future__ import annotations

import json
import uuid

import pytest

from framework import gate
from framework import live
from driver import infra as I
from driver import c_care as CC

CARE = "/api/v1"


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


def _rec(se, method, path, code, body, req=None):
    se.record_raw(method=method, path=path, status=code, request_id="", request_headers={},
                  request_json=req, response_excerpt=json.dumps(body, ensure_ascii=False)[:4000],
                  started_at=0.0, elapsed_ms=0.0)


def _decl(se):
    se.doubles.add("face_algo", "double", "D FaceDouble/MemberBindingFaceDouble（dev 绑定替身）")
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


_BOUND = {"mid": None}


def _bind(mid):
    if _BOUND["mid"] != mid:
        live.java_env_with_bound_member(mid)
        _BOUND["mid"] = mid


def _chain(se):
    g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    assert c == 202 and _worker_until(
        f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{tid}'", 140)
    mid = CC.scalar(f"SELECT member_id::text FROM skin_assessments WHERE id='{tid}'")
    plan = CC.scalar(f"SELECT id::text FROM care_plans WHERE assessment_id='{tid}'")
    app = live.app_login("ob-" + uuid.uuid4().hex[:6])
    serial = f"mc-{uuid.uuid4().hex[:8]}"
    co, bo, _ = live.observe_microcrystal(app, serial, live.CAP_BASELINE)
    _rec(se, "POST", "/api/v1/microcrystal-observations", co, bo, req={"serial": serial})
    assert co == 200
    assert _worker_until(f"SELECT (generation_status='ready')::int FROM care_plans WHERE id='{plan}'", 60)
    mc = CC.scalar(f"SELECT id::text FROM microcrystals WHERE serial_no='{serial}'")
    return {"g": g, "tok": tok, "tid": tid, "mid": mid, "plan": plan, "mc": mc}


def _app_for(mid, tag):
    a = live.app_login(tag)
    CC.seed_grant(a["accountId"], mid, status="active")
    return a


def _device_done(se, n, t=4):
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + gate.device_pending(n, t))


@_mark("SC-00-01", "P0", "联调", ["B","C","D"], [])
def test_SC_00_01(scenario_evidence):
    """全链后端子步骤：受理→报告→方案→APP 授权→A03→A05→A08→A06+控制端指针替换。"""
    se = scenario_evidence
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "s001")
    code, body = CC.admit(a["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", code, body)
    ex = (body.get("data") or {}).get("executionId")
    ep = (body.get("data") or {}).get("recordStreamEpoch") or ex
    rev = CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{ex}'")
    CC.sync(a["access"], ex, CC.obs_records(ep, [CC.rec(ep, 1)], seq=1, state="running", rev=rev),
            str(uuid.uuid4()))
    cp, bp, _ = I.http("GET", f"/api/v1/care-plans/{c['plan']}/progress", token=a["access"])
    _rec(se, "GET", f"/api/v1/care-plans/{c['plan']}/progress", cp, bp)
    CC.sync(a["access"], ex, CC.obs_records(ep, [], seq=2, state="stopped", rev=rev), str(uuid.uuid4()))
    ccl, bcl, _ = CC.closure(a["access"], ex, ep, 1, 1, str(uuid.uuid4()), stop_seq=2)
    _rec(se, "POST", f"{CARE}/care-executions/{ex}/closure-confirmations", ccl, bcl)
    # 控制端指针替换：新云台会话受理新任务，旧任务 closed
    c2 = _chain(se)  # 新云台/新成员/新方案（控制端切换后新流程）
    closed = CC.scalar(f"SELECT (closed_at IS NOT NULL)::int FROM care_executions WHERE id='{ex}'")
    assert code == 201 and cp == 200 and ccl in (200, 201) and closed == "1" and c2["tid"]
    _device_done(se, 4)


@_mark("SC-00-02", "P0", "联调", ["B","C","D"], [])
def test_SC_00_02(scenario_evidence):
    """APP 授权后跨端护理归同一成员/方案：报告/方案/执行查询成员一致。"""
    se = scenario_evidence
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "s002")
    code, body = CC.admit(a["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", code, body)
    ex = (body.get("data") or {}).get("executionId")
    rid = CC.scalar(f"SELECT report_id::text FROM skin_assessments WHERE id='{c['tid']}'")
    c1, b1, _ = I.http("GET", f"/api/v1/members/{c['mid']}/skin-reports", token=a["access"])
    _rec(se, "GET", f"/api/v1/members/{c['mid']}/skin-reports", c1, b1)
    c2, b2, _ = I.http("GET", f"/api/v1/care-plans/{c['plan']}?view=full", token=a["access"])
    _rec(se, "GET", f"/api/v1/care-plans/{c['plan']}?view=full", c2, b2)
    c3, b3, _ = I.http("GET", f"/api/v1/care-executions/{ex}", token=a["access"])
    _rec(se, "GET", f"/api/v1/care-executions/{ex}", c3, b3)
    mrows = [r for r in (
        CC.scalar(f"SELECT member_id::text FROM skin_assessments WHERE id='{c['tid']}'"),
        CC.scalar(f"SELECT member_id::text FROM care_plans WHERE id='{c['plan']}'"),
        CC.scalar(f"SELECT member_id::text FROM care_executions WHERE id='{ex}'"))]
    assert code == 201 and c1 == 200 and c2 == 200 and c3 == 200
    assert len(set(mrows)) == 1 and mrows[0] == c["mid"] and rid
    _device_done(se, 3)


@_mark("SC-00-03", "P0", "联调", ["C"], ["D05"])
def test_SC_00_03(scenario_evidence):
    """控制端切换：旧执行停止对账 closed 后新端登记，同成员同方案沿用 K。"""
    se = scenario_evidence
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "s003")
    k1, b1 = CC.admit(a["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", k1, b1)
    ex = (b1.get("data") or {}).get("executionId")
    ep = (b1.get("data") or {}).get("recordStreamEpoch") or ex
    rev = CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{ex}'")
    CC.sync(a["access"], ex, CC.obs_records(ep, [CC.rec(ep, 1)], seq=1, state="running", rev=rev),
            str(uuid.uuid4()))
    k_before = CC.scalar(f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{c['plan']}'")
    CC.sync(a["access"], ex, CC.obs_records(ep, [], seq=2, state="stopped", rev=rev), str(uuid.uuid4()))
    ccl, bcl, _ = CC.closure(a["access"], ex, ep, 1, 1, str(uuid.uuid4()), stop_seq=2)
    _rec(se, "POST", f"{CARE}/care-executions/{ex}/closure-confirmations", ccl, bcl)
    # 新控制端（另一 APP 会话，同成员）新执行，K 沿用
    a2 = _app_for(c["mid"], "s003b")
    k2, b2 = CC.admit(a2["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", k2, b2, req={"new_controller": True})
    k_after = CC.scalar(f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{c['plan']}'")
    assert k1 == 201 and ccl in (200, 201) and k2 == 201
    assert k_before == k_after == "1"  # 切换不丢已累计 K
    _device_done(se, 3)


@_mark("SC-00-04", "P0", "联调", ["B","D"], ["D01","D02"])
def test_SC_00_04(scenario_evidence):
    """未绑定云台独立认证+测肤；无绑定账号不产生 APP 异常通知（投递面无目标证据）。"""
    se = scenario_evidence
    _decl(se)
    g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b, req={"unbound": True})
    tid = (b.get("data") or {}).get("taskId")
    assert c == 202 and tid
    # 该云台未绑定账号 → 通知目标表无该账号；notifications 无该 gimbal 记录
    bound = CC.scalar(f"SELECT coalesce(bound_account_id::text,'') FROM gimbals WHERE id='{g}'")
    notif = CC.scalar(f"SELECT count(*) FROM notifications WHERE gimbal_id='{g}'")
    assert bound == "" and notif == "0"
    _device_done(se, 3)
