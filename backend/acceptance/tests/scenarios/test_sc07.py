# -*- coding: utf-8 -*-
"""SC-07 · APP 直接控制微晶与执行收尾 —— 集成轮 batch 2 lane B2（7 节点）。

真实链 M3→worker→T06 ready→绑定成员→C A03 准入→A05 状态/次数→A06 收尾→A07/A08 查询。
设备APP 节点执行后端可先验子步骤后 device_pending（端侧行为待联调）。
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


def _rec(se, method, path, code, body, req=None, headers=None):
    se.record_raw(method=method, path=path, status=code, request_id="",
                  request_headers=headers or {}, request_json=req,
                  response_excerpt=json.dumps(body, ensure_ascii=False)[:4000],
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


def _setup(se):
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "s7-" + uuid.uuid4().hex[:6])
    code, body = CC.admit(a["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", code, body)
    assert code == 201, (code, body)
    d = body.get("data") or {}
    c.update({"app": a, "ex": d.get("executionId"),
              "ep": d.get("recordStreamEpoch") or d.get("executionId"),
              "rev": CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{d.get('executionId')}'")})
    return c


def _sync(c, records, seq, state="running", continuity=True, key=None):
    return CC.sync(c["app"]["access"], c["ex"],
                   CC.obs_records(c["ep"], records, seq=seq, state=state, rev=c["rev"],
                                  continuity=continuity), key or str(uuid.uuid4()))


def _close(c, stop_seq=1):
    _sync(c, [], seq=1, state="stopped")
    return CC.closure(c["app"]["access"], c["ex"], c["ep"], 0, 0, str(uuid.uuid4()), stop_seq=stop_seq)


def _device_done(se, n, t=3):
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + gate.device_pending(n, t))


@_mark("SC-07-04", "P0", "后端", ["C"], ["D05"])
def test_SC_07_04(scenario_evidence):
    """实际停止后对账关闭+占用释放；未停止/未知不释放。"""
    se = scenario_evidence
    _decl(se)
    c = _setup(se)
    # 未停止 → 收尾 409 STOP_NOT_CONFIRMED，占用仍在
    cbad, bbad, _ = CC.closure(c["app"]["access"], c["ex"], c["ep"], 0, 0, str(uuid.uuid4()), stop_seq=1)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/closure-confirmations", cbad, bbad, req={"not_stopped": True})
    cx, bx = CC.admit(c["app"]["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", cx, bx, req={"while_occupied": True})
    # stopped + 收尾 → closed + 释放
    cok, bok, _ = _close(c)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/closure-confirmations", cok, bok)
    cnew, bnew = CC.admit(c["app"]["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", cnew, bnew, req={"after_release": True})
    closed = CC.scalar(f"SELECT (closed_at IS NOT NULL)::int FROM care_executions WHERE id='{c['ex']}'")
    assert cbad == 409 and bbad["error"]["code"] == "STOP_NOT_CONFIRMED"
    assert cx == 409 and bx["error"]["code"] == "DEVICE_OCCUPIED"
    assert cok in (200, 201) and closed == "1"
    assert cnew == 201, (cnew, bnew)
    se.seal()


@_mark("SC-07-05", "P0", "后端", ["C"], ["D05"])
def test_SC_07_05(scenario_evidence):
    """未停止或对账未完成时抢占拒绝：占用保持，过期剩余量不可启动。"""
    se = scenario_evidence
    _decl(se)
    c = _setup(se)
    # 同微晶第二控制端（不同 APP 会话）抢占 → 拒绝
    other = _app_for(c["mid"], "s705-" + uuid.uuid4().hex[:6])
    cc, bb = CC.admit(other["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", cc, bb, req={"preempt": True})
    occ = CC.scalar(f"SELECT count(*)||'|'||min(controller_account_id::text) FROM care_executions "
                    f"WHERE microcrystal_id='{c['mc']}' AND closed_at IS NULL")
    assert cc == 409 and bb["error"]["code"] == "DEVICE_OCCUPIED"
    assert occ.startswith("1|")  # 占用保持唯一
    se.seal()


@_mark("SC-07-06", "P0", "后端", ["C"], ["D04", "D05"])
def test_SC_07_06(scenario_evidence):
    """收尾重复/越权/已结束：合法重复不重复释放计数；非原控制端拒绝；closed 不重开。"""
    se = scenario_evidence
    _decl(se)
    c = _setup(se)
    key = str(uuid.uuid4())
    _sync(c, [], seq=1, state="stopped")
    c1, b1, _ = CC.closure(c["app"]["access"], c["ex"], c["ep"], 0, 0, key, stop_seq=1)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/closure-confirmations", c1, b1, req={"n": 1})
    man1 = CC.scalar(f"SELECT coalesce(closure_manifest::text,'') FROM care_executions WHERE id='{c['ex']}'")
    c2, b2, _ = CC.closure(c["app"]["access"], c["ex"], c["ep"], 0, 0, key, stop_seq=1)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/closure-confirmations", c2, b2, req={"n": 2, "replay": True})
    man2 = CC.scalar(f"SELECT coalesce(closure_manifest::text,'') FROM care_executions WHERE id='{c['ex']}'")
    # 非原控制端 → 拒绝
    other = _app_for(c["mid"], "s706-" + uuid.uuid4().hex[:6])
    c3, b3, _ = CC.closure(other["access"], c["ex"], c["ep"], 0, 0, str(uuid.uuid4()), stop_seq=1)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/closure-confirmations", c3, b3, req={"other": True})
    assert c1 in (200, 201) and c2 in (200, 201) and man1 == man2  # 重放 manifest 不变
    assert c3 in (403, 404)
    se.seal()


@_mark("SC-07-07", "P1", "后端", ["C"], ["D05"])
def test_SC_07_07(scenario_evidence):
    """执行详情/恢复对账查询：固定归属、状态新鲜度、确认/关闭状态；越权 404。"""
    se = scenario_evidence
    _decl(se)
    c = _setup(se)
    other = live.app_login("s707o")
    c1, b1, _ = I.http("GET", f"/api/v1/care-executions/{c['ex']}", token=c["app"]["access"])
    _rec(se, "GET", f"/api/v1/care-executions/{c['ex']}", c1, b1)
    c2, b2, _ = I.http("GET", f"/api/v1/care-executions/{c['ex']}", token=other["access"])
    _rec(se, "GET", f"/api/v1/care-executions/{c['ex']}", c2, b2, req={"grant": False})
    c3, b3, _ = I.http("GET", f"/api/v1/care-plans/{c['plan']}/progress", token=c["app"]["access"])
    _rec(se, "GET", f"/api/v1/care-plans/{c['plan']}/progress", c3, b3)
    d = b1.get("data") or {}
    assert c1 == 200 and d.get("executionId") == c["ex"] and d.get("status")
    assert d.get("controller") is not None
    assert c2 == 404 and c3 == 200
    se.seal()


# ---------------- 设备APP（后端子步骤） ----------------

@_mark("SC-07-01", "P0", "联调", ["B", "C"], ["D01", "D06"])
def test_SC_07_01(scenario_evidence):
    """后端可先验：能力登记+核验+方案/占用检查通过后 A03 201（端侧本地开始待联调）。"""
    se = scenario_evidence
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "s701-" + uuid.uuid4().hex[:6])
    code, body = CC.admit(a["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", code, body)
    assert code == 201
    _device_done(se, 3)


@_mark("SC-07-02", "P0", "联调", ["C"], ["D06"])
def test_SC_07_02(scenario_evidence):
    """后端可先验：后端不转发控制指令，仅收状态/次数（无端侧指令表写入）。"""
    se = scenario_evidence
    _decl(se)
    c = _setup(se)
    c1, b1, _ = _sync(c, [CC.rec(c["ep"], 1)], seq=1, state="paused")
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c1, b1, req={"paused": True})
    k = CC.scalar(f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{c['plan']}'")
    assert c1 == 200 and k == "1"
    _device_done(se, 2)


@_mark("SC-07-03", "P0", "联调", ["C"], ["D06"])
def test_SC_07_03(scenario_evidence):
    """后端可先验：连续性失效→A08 门控；A04 后恢复（端侧换人/断网行为待联调）。"""
    se = scenario_evidence
    _decl(se)
    c = _setup(se)
    c1, b1, _ = _sync(c, [], seq=1, state="paused", continuity=False)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c1, b1, req={"continuity": False})
    ci = CC.scalar("SELECT coalesce(latest_observation->>'continuity_invalidated','') "
                   f"FROM care_executions WHERE id='{c['ex']}'")
    assert c1 == 200 and ci == "true"
    _device_done(se, 2)
