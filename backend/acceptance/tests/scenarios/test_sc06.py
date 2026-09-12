# -*- coding: utf-8 -*-
"""SC-06 · 实际次数、去重与累计进度 —— 集成轮 batch 2 lane B2（9 节点）。

真实链：M3→worker→T06 ready→（真实 M2-A04 补齐）→绑定成员→C A03 准入→A05 记账→A06 收尾。
场景级断言走真实链上下文（非 c_care 种子捷径）；SQL 侧证 K/completed_at/late_variance。
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


def _bind(mid: str | None):
    if _BOUND["mid"] != mid:
        live.java_env_with_bound_member(mid)
        _BOUND["mid"] = mid


def _chain(se, target: int | None = None):
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
    if target is not None:
        CC.sql(f"UPDATE care_plans SET target_count={target} WHERE id='{plan}'")
    return {"g": g, "tok": tok, "tid": tid, "mid": mid, "plan": plan, "mc": mc}


def _app_for(mid, tag):
    a = live.app_login(tag)
    CC.seed_grant(a["accountId"], mid, status="active")
    return a


def _admit(app, ctx, key=None, metadata=None):
    return CC.admit(app["access"], ctx["mc"], ctx["plan"],
                    key=key or str(uuid.uuid4()), metadata=metadata)


def _ctx_after_admit(se, target=None):
    c = _chain(se, target=target)
    _bind(c["mid"])
    a = _app_for(c["mid"], "s6-" + uuid.uuid4().hex[:6])
    code, body = _admit(a, c)
    _rec(se, "POST", "/api/v1/care-executions", code, body)
    assert code == 201, (code, body)
    d = body.get("data") or {}
    c.update({"app": a, "ex": d.get("executionId"), "ep": d.get("recordStreamEpoch") or d.get("executionId"),
              "rev": CC.scalar(f"SELECT verification_revision FROM care_executions "
                               f"WHERE id='{d.get('executionId')}'")})
    return c


def _k(plan):
    return CC.scalar(f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{plan}'")


def _cata(plan):
    return CC.scalar(f"SELECT coalesce(completed_at::text,'') FROM care_plans WHERE id='{plan}'")


def _sync(c, records, seq, state="running", continuity=True, key=None):
    return CC.sync(c["app"]["access"], c["ex"],
                   CC.obs_records(c["ep"], records, seq=seq, state=state, rev=c["rev"],
                                  continuity=continuity), key or str(uuid.uuid4()))


def _device_done(se, n, t=3):
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + gate.device_pending(n, t))


@_mark("SC-06-01", "P0", "后端", ["C"], [])
def test_SC_06_01(scenario_evidence):
    """有效记录累计及目标边界：N=10，K=9/10/11；completed_at 首达不改写；K 不截断。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx_after_admit(se, target=10)
    c1, b1, _ = _sync(c, [CC.rec(c["ep"], i) for i in range(1, 10)], seq=1)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c1, b1, req={"records": "1..9"})
    k9, ca9 = _k(c["plan"]), _cata(c["plan"])
    c2, b2, _ = _sync(c, [CC.rec(c["ep"], 10)], seq=2)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c2, b2, req={"records": "10"})
    k10, ca10 = _k(c["plan"]), _cata(c["plan"])
    c3, b3, _ = _sync(c, [CC.rec(c["ep"], 11)], seq=3)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c3, b3, req={"records": "11"})
    k11, ca11 = _k(c["plan"]), _cata(c["plan"])
    assert c1 == 200 and k9 == "9" and ca9 == ""
    assert c2 == 200 and k10 == "10" and ca10
    assert c3 == 200 and k11 == "11" and ca11 == ca10  # 首达不改写、不截断
    se.seal()


@_mark("SC-06-02", "P0", "后端", ["C"], ["D04"])
def test_SC_06_02(scenario_evidence):
    """重复记录只计一次；同标识不同内容冲突；逐记录确认范围。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx_after_admit(se, target=10)
    body = CC.obs_records(c["ep"], [CC.rec(c["ep"], 1, delta="1"), CC.rec(c["ep"], 1, delta="1")],
                          seq=1, state="running", rev=c["rev"])
    key = str(uuid.uuid4())
    c1, b1, _ = CC.sync(c["app"]["access"], c["ex"], body, key)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c1, b1, req={"batch_dup": True})
    k1 = _k(c["plan"])
    c2, b2, _ = CC.sync(c["app"]["access"], c["ex"], body, key)  # 同键同内容 → 重放
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c2, b2, req={"replay": True})
    k2 = _k(c["plan"])
    c3, b3, _ = _sync(c, [CC.rec(c["ep"], 1, delta="2")], seq=2)  # 同标识异内容 → 冲突
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c3, b3, req={"conflict": True})
    assert c1 == 200 and k1 == "1"  # 批内重复只计一次
    assert c2 == 200 and k2 == "1"  # 幂等重放
    assert c3 == 409 and b3["error"]["code"] == "RECORD_CONFLICT"
    se.seal()


@_mark("SC-06-03", "P0", "后端", ["C"], ["D01"])
def test_SC_06_03(scenario_evidence):
    """记录归属校验：epoch 不符的记录不得计入 K。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx_after_admit(se, target=10)
    bogus = f"epoch-{uuid.uuid4().hex[:8]}"
    c1, b1, _ = _sync(c, [CC.rec(bogus, 1)], seq=1, key=str(uuid.uuid4()))
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c1, b1, req={"epoch": "bogus"})
    assert _k(c["plan"]) == "0", _k(c["plan"])
    se.seal()


@_mark("SC-06-04", "P0", "后端", ["C"], [])
def test_SC_06_04(scenario_evidence):
    """状态上报≠实际次数：仅状态变化不计完成。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx_after_admit(se, target=10)
    c1, b1, _ = _sync(c, [], seq=1, state="running")
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c1, b1, req={"state_only": True})
    assert c1 == 200 and _k(c["plan"]) == "0"
    se.seal()


@_mark("SC-06-05", "P0", "联调", ["C"], ["D04"])
def test_SC_06_05(scenario_evidence):
    """后端可先验：断网补传去重不丢已收合法次数；客户端缓存行为待联调。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx_after_admit(se, target=10)
    c1, b1, _ = _sync(c, [CC.rec(c["ep"], 1), CC.rec(c["ep"], 2)], seq=1)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c1, b1, req={"n": 1})
    k1 = _k(c["plan"])
    c2, b2, _ = _sync(c, [CC.rec(c["ep"], 1), CC.rec(c["ep"], 2), CC.rec(c["ep"], 3)], seq=2)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", c2, b2, req={"n": 2, "resend": True})
    k2 = _k(c["plan"])
    assert c1 == 200 and k1 == "2" and c2 == 200 and k2 == "3"
    _device_done(se, 2)


@_mark("SC-06-06", "P0", "后端", ["C"], [])
def test_SC_06_06(scenario_evidence):
    """迟到记录：已结束执行可收合法历史、旧 running 不重开、迟到归原方案+late_variance 留痕。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx_after_admit(se, target=10)
    _sync(c, [CC.rec(c["ep"], 1)], seq=1)
    _sync(c, [], seq=2, state="stopped")
    ccl, bcl, _ = CC.closure(c["app"]["access"], c["ex"], c["ep"], 1, 1, str(uuid.uuid4()), stop_seq=2)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/closure-confirmations", ccl, bcl)
    closed = CC.scalar(f"SELECT (closed_at IS NOT NULL)::int FROM care_executions WHERE id='{c['ex']}'")
    k_before = _k(c["plan"])
    clate, blate, _ = _sync(c, [CC.rec(c["ep"], 2)], seq=3)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", clate, blate, req={"late": True})
    k_after = _k(c["plan"])
    status = CC.scalar(f"SELECT status FROM care_executions WHERE id='{c['ex']}'")
    lv = CC.scalar("SELECT coalesce(closure_manifest->>'late_variance','') "
                   f"FROM care_executions WHERE id='{c['ex']}'")
    assert ccl in (200, 201) and closed == "1"
    assert clate == 200 and int(k_after) == int(k_before) + 1
    assert status == "closed" and lv not in ("", "null")  # 迟到留痕、不重开
    se.seal()


@_mark("SC-06-07", "P0", "后端", ["C"], [])
def test_SC_06_07(scenario_evidence):
    """方案完成后禁止新执行：K≥N 拒新登记；合法历史补传仍接收且不重开。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx_after_admit(se, target=1)
    _sync(c, [CC.rec(c["ep"], 1)], seq=1)
    assert _k(c["plan"]) == "1"
    cc, bb = _admit(c["app"], c)
    _rec(se, "POST", "/api/v1/care-executions", cc, bb, req={"after_completed": True})
    clate, blate, _ = _sync(c, [CC.rec(c["ep"], 2)], seq=2)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/observations", clate, blate, req={"late": True})
    assert cc == 409 and bb["error"]["code"] == "PLAN_COMPLETED"
    assert clate == 200 and int(_k(c["plan"])) >= 2
    se.seal()


@_mark("SC-06-08", "P1", "后端", ["C"], [])
def test_SC_06_08(scenario_evidence):
    """进度查询范围与新鲜度：APP 须授权；仅已同步 K+最后同步；越权 404。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx_after_admit(se, target=10)
    _sync(c, [CC.rec(c["ep"], 1)], seq=1)
    other = live.app_login("s608o")
    c1, b1, _ = I.http("GET", f"/api/v1/care-plans/{c['plan']}/progress", token=c["app"]["access"])
    _rec(se, "GET", f"/api/v1/care-plans/{c['plan']}/progress", c1, b1, req={"grant": True})
    c2, b2, _ = I.http("GET", f"/api/v1/care-plans/{c['plan']}/progress", token=other["access"])
    _rec(se, "GET", f"/api/v1/care-plans/{c['plan']}/progress", c2, b2, req={"grant": False})
    d = b1.get("data") or {}
    assert c1 == 200 and str(d.get("completedCount")) == "1" and d.get("targetCount") == "10"
    assert "lastSyncedAt" in json.dumps(d)
    assert c2 == 404 and b2["error"]["code"] == "RESOURCE_NOT_VISIBLE"
    se.seal()


@_mark("SC-06-09", "P1", "后端", ["C"], ["D08"])
def test_SC_06_09(scenario_evidence):
    """护理历史查询：权限/筛选；执行结束与方案完成分显；不串人/串方案。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx_after_admit(se, target=1)
    _sync(c, [CC.rec(c["ep"], 1)], seq=1)
    other = live.app_login("s609o")
    c1, b1, _ = I.http("GET", f"/api/v1/members/{c['mid']}/care-executions", token=c["app"]["access"])
    _rec(se, "GET", f"/api/v1/members/{c['mid']}/care-executions", c1, b1)
    c2, b2, _ = I.http("GET", f"/api/v1/members/{c['mid']}/care-executions", token=other["access"])
    _rec(se, "GET", f"/api/v1/members/{c['mid']}/care-executions", c2, b2, req={"grant": False})
    items = (b1.get("data") or {}).get("items") or []
    assert c1 == 200 and any(it.get("executionId") == c["ex"] for it in items)
    assert c2 == 404
    se.seal()
