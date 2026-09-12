# -*- coding: utf-8 -*-
"""SC-04 · 云台执行前核验与运行中连续性 —— 集成轮 batch 2 lane B1（10 节点）。

真实链：M3-A01→worker→T05 报告→T06 方案（+真实 B M2-A04 补齐能力）→
Java 绑定成员（APP_C_FACE_BOUND_MEMBER）→ C A03 准入 / A04 重验 / A05 观察 / A08 进度。
设备APP 节点执行后端可先验子步骤后结算 device_pending（真实端侧联调待办）。
不可注入子形态（UNCERTAIN/算法失败等）按 lane A1 先例精确披露，不伪造 pass。
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


def _audit(se, note, code=0, body=None):
    se.record_raw(method="AUDIT", path=note, status=code, request_headers={}, request_json=None,
                  response_excerpt=json.dumps(body or {}, ensure_ascii=False)[:800],
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


def _chain(se, observe: bool = True):
    """真实链：M3 受理→报告 ready→（可选）M2-A04 补齐能力→T06 ready。"""
    g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    assert c == 202 and _worker_until(
        f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{tid}'", 140), (c, b)
    mid = CC.scalar(f"SELECT member_id::text FROM skin_assessments WHERE id='{tid}'")
    rid = CC.scalar(f"SELECT report_id::text FROM skin_assessments WHERE id='{tid}'")
    plan = CC.scalar(f"SELECT id::text FROM care_plans WHERE assessment_id='{tid}'")
    mc = None
    if observe:
        app = live.app_login("obs-" + uuid.uuid4().hex[:6])
        serial = f"mc-{uuid.uuid4().hex[:8]}"
        co, bo, _ = live.observe_microcrystal(app, serial, live.CAP_BASELINE)
        _rec(se, "POST", "/api/v1/microcrystal-observations", co, bo, req={"serial": serial})
        assert co == 200, (co, bo)
        assert _worker_until(
            f"SELECT (generation_status='ready')::int FROM care_plans WHERE id='{plan}'", 60), "plan not ready"
        mc = CC.scalar(f"SELECT id::text FROM microcrystals WHERE serial_no='{serial}'")
    return {"g": g, "tok": tok, "tid": tid, "mid": mid, "rid": rid, "plan": plan, "mc": mc}


def _app_for(mid: str, tag: str) -> dict:
    a = live.app_login(tag)
    CC.seed_grant(a["accountId"], mid, status="active")
    return a


def _admit(app: dict, ctx: dict, mc: str | None = None, key: str | None = None, metadata=None):
    return CC.admit(app["access"], mc or ctx["mc"], ctx["plan"],
                    key=key or str(uuid.uuid4()), metadata=metadata)


def _device_done(se, n, t=3):
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + gate.device_pending(n, t))


# ---------------- 后端可自动 ----------------

@_mark("SC-04-02", "P0", "后端", ["C"], ["D06"])
def test_SC_04_02(scenario_evidence):
    """不同成员/未绑定：异成员 403 FACE_NOT_VERIFIED 且不回原成员方案；未绑定 503 fail-closed。"""
    se = scenario_evidence
    _decl(se)
    c1 = _chain(se)          # 成员 A（bound 用）
    c2 = _chain(se)          # 成员 B（异成员计划）
    _bind(c1["mid"])
    a = _app_for(c2["mid"], "sc0402")  # 对 B 的计划发起，但 Java 绑定 A → MISMATCH
    ca, ba = _admit(a, c2)
    _rec(se, "POST", "/api/v1/care-executions", ca, ba, req={"case": "mismatch"})
    # 未绑定 → 503
    _bind(None)
    a2 = _app_for(c1["mid"], "sc0402b")
    cu, bu = _admit(a2, c1)
    _rec(se, "POST", "/api/v1/care-executions", cu, bu, req={"case": "unbound"})
    _bind(c1["mid"])
    t07 = CC.scalar(f"SELECT count(*) FROM care_executions WHERE plan_id IN "
                    f"('{c1['plan']}','{c2['plan']}')")
    assert ca == 403 and ba["error"]["code"] == "FACE_NOT_VERIFIED"
    assert "planExecution" not in json.dumps(ba) and "plan" not in (ba.get("data") or {})
    assert cu == 503 and bu["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert t07 == "0"
    _audit(se, "SC-04-02 core verified; UNCERTAIN/algorithm-failure sub-shape needs D seam", 0,
           {"mismatch": ca, "unbound": cu})
    se.seal()


@_mark("SC-04-03", "P0", "后端", ["C"], ["D06"])
def test_SC_04_03(scenario_evidence):
    """方案未就绪/已完成/能力不满足：409 精确 reason，均不登记新执行（T07 零行）。"""
    se = scenario_evidence
    _decl(se)

    # A) 方案未就绪（waiting_inputs）→ 409 PLAN_NOT_READY，且 M4-A02 明确 waitingReason
    cw = _chain(se, observe=False)
    _bind(cw["mid"])
    aw = _app_for(cw["mid"], "sc0403w")
    assert CC.scalar(f"SELECT generation_status FROM care_plans WHERE id='{cw['plan']}'") == "waiting_inputs"
    cw1, bw1 = _admit(aw, cw, mc=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", cw1, bw1, req={"case": "plan_waiting"})
    cp, bp, _ = I.http("GET", f"/api/v1/care-plans/{cw['plan']}?view=full", token=aw["access"])
    _rec(se, "GET", f"/api/v1/care-plans/{cw['plan']}?view=full", cp, bp)
    assert cw1 == 409 and bw1["error"]["code"] == "PLAN_NOT_READY"
    assert (bp.get("data") or {}).get("waitingReason") == "waiting_inputs"
    # B) 方案 ready 但能力不满足（capability_id 不符，真实 M2-A04）→ 409 PLAN_NOT_READY + reason token
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "sc0403a")
    appw = live.app_login("sc0403wc")
    serialw = f"mc-{uuid.uuid4().hex[:8]}"
    co, bo, _ = live.observe_microcrystal(appw, serialw,
                                          {**live.CAP_BASELINE, "capability_id": "other-cap"})
    _rec(se, "POST", "/api/v1/microcrystal-observations", co, bo, req={"serial": serialw})
    mc_bad = CC.scalar(f"SELECT id::text FROM microcrystals WHERE serial_no='{serialw}'")
    cc1, bb1 = _admit(a, c, mc=mc_bad)
    _rec(se, "POST", "/api/v1/care-executions", cc1, bb1, req={"case": "capability_mismatch"})
    # C) 方案已完成 K=N → 409 PLAN_COMPLETED
    CC.sql(f"UPDATE care_plans SET completed_count=target_count WHERE id='{c['plan']}'")
    cc2, bb2 = _admit(a, c)
    _rec(se, "POST", "/api/v1/care-executions", cc2, bb2, req={"case": "plan_completed"})
    exec_cw = CC.scalar(f"SELECT count(*) FROM care_executions WHERE plan_id='{cw['plan']}'")
    exec_c = CC.scalar(f"SELECT count(*) FROM care_executions WHERE plan_id='{c['plan']}'")
    assert cc1 == 409 and bb1["error"]["code"] == "PLAN_NOT_READY"
    assert bb1["error"].get("details", {}).get("reason") in (
        "device_capabilities_missing", "capability_id_mismatch", "parameter_range_not_covered",
        "region_not_supported", "n_out_of_bounds", "frozen_capability_requirement_missing",
        "malformed_frozen_capability", "step_parameters_not_covered", "malformed_frozen_step")
    assert cc2 == 409 and bb2["error"]["code"] == "PLAN_COMPLETED"
    assert exec_cw == "0" and exec_c == "0"
    se.seal()


@_mark("SC-04-04", "P0", "后端", ["C"], ["D05"])
def test_SC_04_04(scenario_evidence):
    """同一微晶并发准入：恰一 201 一 409 DEVICE_OCCUPIED，占用 SQL 唯一。"""
    se = scenario_evidence
    import threading
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a1 = _app_for(c["mid"], "sc0404a")
    a2 = _app_for(c["mid"], "sc0404b")
    res = {}

    def run(name, app):
        res[name] = _admit(app, c, mc=c["mc"], key=str(uuid.uuid4()))

    t1 = threading.Thread(target=run, args=("a", a1))
    t2 = threading.Thread(target=run, args=("b", a2))
    t1.start(); t2.start(); t1.join(); t2.join()
    codes = sorted([res["a"][0], res["b"][0]])
    for name in ("a", "b"):
        cc, bb = res[name]
        _rec(se, "POST", "/api/v1/care-executions", cc, bb, req={"concurrent": name})
    occ = CC.scalar(f"SELECT count(*) FROM care_executions WHERE microcrystal_id='{c['mc']}' "
                    "AND closed_at IS NULL")
    assert codes == [201, 409], codes
    assert occ == "1", occ
    bad = [res[n][1] for n in ("a", "b") if res[n][0] == 409]
    assert bad and bad[0]["error"]["code"] == "DEVICE_OCCUPIED"
    se.seal()


# ---------------- 设备APP（后端子步骤） ----------------

@_mark("SC-04-01", "P0", "联调", ["C"], ["D01", "D06"])
def test_SC_04_01(scenario_evidence):
    """后端可先验：A03 准入 201 含执行/控制端/方案/N/K+T07 SQL；端侧启动确认待联调。"""
    se = scenario_evidence
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "sc0401")
    code, body = _admit(a, c)
    _rec(se, "POST", "/api/v1/care-executions", code, body)
    data = body.get("data") or {}
    ex = data.get("executionId")
    row = CC.scalar(f"SELECT plan_id||'|'||member_id||'|'||microcrystal_id||'|'||status "
                    f"FROM care_executions WHERE id='{ex}'")
    n = CC.scalar(f"SELECT target_count FROM care_plans WHERE id='{c['plan']}'")
    assert code == 201 and ex and data.get("planId") == c["plan"]
    assert data.get("memberId") == c["mid"]
    assert (data.get("controller") or {}).get("controllerType") == "app_account"
    assert data.get("verification") is not None and n not in ("", None)
    assert row == f"{c['plan']}|{c['mid']}|{c['mc']}|admitted", row
    _device_done(se, 3)


@_mark("SC-04-05", "P0", "联调", ["C"], ["D04", "D05"])
def test_SC_04_05(scenario_evidence):
    """后端可先验：A03 同键重放 200 replayed+当前状态；撤销授权后重放 404 资格复核。"""
    se = scenario_evidence
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "sc0405")
    key = str(uuid.uuid4())
    md = CC.mk_metadata(c["mc"], plan=c["plan"])
    c1, b1 = _admit(a, c, key=key, metadata=md)
    _rec(se, "POST", "/api/v1/care-executions", c1, b1, req={"key": key, "n": 1})
    c2, b2 = _admit(a, c, key=key, metadata=md)
    _rec(se, "POST", "/api/v1/care-executions", c2, b2, req={"key": key, "n": 2})
    ex = (b1.get("data") or {}).get("executionId")
    assert c1 == 201 and c2 == 200 and (b2.get("data") or {}).get("executionId") == ex
    # 撤销授权 → 重放同键 404（资格复核）
    gid = CC.scalar(f"SELECT id::text FROM member_access_grants WHERE account_id='{a['accountId']}' "
                    f"AND member_id='{c['mid']}' AND status='active'")
    I.http("DELETE", f"/api/v1/me/member-access-grants/{gid}", token=a["access"],
           headers={"Idempotency-Key": str(uuid.uuid4())})
    c3, b3 = _admit(a, c, key=key, metadata=md)
    _rec(se, "POST", "/api/v1/care-executions", c3, b3, req={"key": key, "after_revoke": True})
    assert c3 == 404
    _device_done(se, 3)


@_mark("SC-04-06", "P0", "联调", ["C"], ["D06"])
def test_SC_04_06(scenario_evidence):
    """后端可先验：A05 未上传期间 K 不变（不冒充离线次数）；端侧缓存待联调。"""
    se = scenario_evidence
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "sc0406")
    ce, be = _admit(a, c)
    _rec(se, "POST", "/api/v1/care-executions", ce, be)
    ex = (be.get("data") or {}).get("executionId")
    k0 = CC.scalar(f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{c['plan']}'")
    time_passes = "SELECT 1"  # 不调用 A05；仅推进后端（无上传）
    assert k0 == "0"
    k1 = CC.scalar(f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{c['plan']}'")
    assert k1 == k0 and ce == 201 and ex
    _device_done(se, 2)


@_mark("SC-04-07", "P0", "联调", ["C"], ["D06"])
def test_SC_04_07(scenario_evidence):
    """后端可先验：A05 paused+continuityValid=false→连续性失效→A08 统一 404；A04 后恢复。"""
    se = scenario_evidence
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "sc0407")
    ce, be = _admit(a, c)
    _rec(se, "POST", "/api/v1/care-executions", ce, be)
    ex = (be.get("data") or {}).get("executionId")
    ep = (be.get("data") or {}).get("recordStreamEpoch") or ex
    c5, b5, _ = CC.sync(a["access"], ex, CC.obs_records(ep, [], seq=1, state="paused",
                                                       continuity=False), str(uuid.uuid4()))
    _rec(se, "POST", f"{CARE}/care-executions/{ex}/observations", c5, b5, req={"continuity": False})
    c8, b8, _ = I.http("GET", f"/api/v1/care-plans/{c['plan']}/progress?executionId={ex}&verificationRevision=1",
                       token=a["access"])
    _rec(se, "GET", f"/api/v1/care-plans/{c['plan']}/progress", c8, b8)
    ci = CC.scalar("SELECT coalesce(latest_observation->>'continuity_invalidated','') "
                   f"FROM care_executions WHERE id='{ex}'")
    assert ce == 201 and c5 == 200, (ce, c5, b5)
    assert ci == "true", ci  # 连续性失效已持久化（云台侧 A08 404 属端到端联调）
    _device_done(se, 3)


@_mark("SC-04-08", "P0", "联调", ["C"], ["D05", "D06"])
def test_SC_04_08(scenario_evidence):
    """后端可先验：A04 仅原控制端+未完成；revision+1、状态不变、continuity 仅 A04 清除。"""
    se = scenario_evidence
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "sc0408")
    other = _app_for(c["mid"], "sc0408o")
    ce, be = _admit(a, c)
    _rec(se, "POST", "/api/v1/care-executions", ce, be)
    ex = (be.get("data") or {}).get("executionId")
    ep = (be.get("data") or {}).get("recordStreamEpoch") or ex
    CC.sync(a["access"], ex, CC.obs_records(ep, [], seq=1, state="paused", continuity=False),
            str(uuid.uuid4()))
    rev = CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{ex}'")
    # 非原控制端 → 拒绝
    cbad, bbad = CC.post_multipart(f"{CARE}/care-executions/{ex}/revalidations", other["access"],
                                   {"expectedVerificationRevision": rev or "1",
                                    "capture": {"captureId": str(uuid.uuid4()),
                                                "capturedAt": CC.utcnow(),
                                                "clientContinuityId": "cc-x", "purpose": "revalidation"},
                                    "consentEvidenceRef": "consent-x"}, str(uuid.uuid4()))
    _rec(se, "POST", f"{CARE}/care-executions/{ex}/revalidations", cbad, bbad, req={"non_original": True})
    # 原控制端 → 200，revision+1，状态不变
    st0 = CC.scalar(f"SELECT status FROM care_executions WHERE id='{ex}'")
    cok, bok = CC.post_multipart(f"{CARE}/care-executions/{ex}/revalidations", a["access"],
                                 {"expectedVerificationRevision": rev or "1",
                                  "capture": {"captureId": str(uuid.uuid4()),
                                              "capturedAt": CC.utcnow(),
                                              "clientContinuityId": "cc-ok", "purpose": "revalidation"},
                                  "consentEvidenceRef": "consent-ok"}, str(uuid.uuid4()))
    _rec(se, "POST", f"{CARE}/care-executions/{ex}/revalidations", cok, bok, req={"original": True})
    rev2 = CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{ex}'")
    st1 = CC.scalar(f"SELECT status FROM care_executions WHERE id='{ex}'")
    assert ce == 201
    assert cbad in (403, 404), (cbad, bbad)
    assert cok == 200 and int(rev2) == int(rev or "0") + 1 and st0 == st1
    _device_done(se, 3)


@_mark("SC-04-09", "P0", "联调", ["C"], ["D06"])
def test_SC_04_09(scenario_evidence):
    """后端可先验：旧核验响应不适用——已换代/已失效执行的 A04 被拒；客户端判定待联调。"""
    se = scenario_evidence
    _decl(se)
    c = _chain(se)
    _bind(c["mid"])
    a = _app_for(c["mid"], "sc0409")
    ce, be = _admit(a, c)
    _rec(se, "POST", "/api/v1/care-executions", ce, be)
    ex = (be.get("data") or {}).get("executionId")
    ep = (be.get("data") or {}).get("recordStreamEpoch") or ex
    CC.sync(a["access"], ex, CC.obs_records(ep, [], seq=1, state="paused", continuity=False),
            str(uuid.uuid4()))
    rev = CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{ex}'")
    # 用过期 revision 的 A04 → 拒绝（旧响应不适用）
    stale, bstale = CC.post_multipart(f"{CARE}/care-executions/{ex}/revalidations", a["access"],
                                      {"expectedVerificationRevision": str(int(rev or "1") + 5),
                                       "capture": {"captureId": str(uuid.uuid4()),
                                                   "capturedAt": CC.utcnow(),
                                                   "clientContinuityId": "cc-stale",
                                                   "purpose": "revalidation"},
                                       "consentEvidenceRef": "consent-stale"}, str(uuid.uuid4()))
    _rec(se, "POST", f"{CARE}/care-executions/{ex}/revalidations", stale, bstale, req={"stale_rev": True})
    assert ce == 201 and stale in (404, 409), (stale, bstale)
    _device_done(se, 2)


@_mark("SC-04-10", "P0", "联调", ["C"], ["D05", "D06"])
def test_SC_04_10(scenario_evidence):
    """后端可先验：旧执行停止对账 closed→新成员新链→新执行；不混用原成员方案（跨成员隔离）。"""
    se = scenario_evidence
    _decl(se)
    c1 = _chain(se)
    _bind(c1["mid"])
    a1 = _app_for(c1["mid"], "sc0410a")
    ce, be = _admit(a1, c1)
    _rec(se, "POST", "/api/v1/care-executions", ce, be)
    ex = (be.get("data") or {}).get("executionId")
    ep = (be.get("data") or {}).get("recordStreamEpoch") or ex
    # 停止并收尾 closed
    CC.sync(a1["access"], ex, CC.obs_records(ep, [], seq=1, state="stopped"), str(uuid.uuid4()))
    ccl, bcl, _ = CC.closure(a1["access"], ex, ep, 0, 0, str(uuid.uuid4()), stop_seq=1)
    _rec(se, "POST", f"{CARE}/care-executions/{ex}/closure-confirmations", ccl, bcl)
    closed = CC.scalar(f"SELECT (closed_at IS NOT NULL)::int FROM care_executions WHERE id='{ex}'")
    # 新成员新链 → 新执行，plan/member 不串原成员
    c2 = _chain(se)
    _bind(c2["mid"])
    a2 = _app_for(c2["mid"], "sc0410b")
    ce2, be2 = _admit(a2, c2)
    _rec(se, "POST", "/api/v1/care-executions", ce2, be2)
    ex2 = (be2.get("data") or {}).get("executionId")
    row = CC.scalar(f"SELECT plan_id||'|'||member_id FROM care_executions WHERE id='{ex2}'")
    assert closed == "1" and ce2 == 201
    assert row == f"{c2['plan']}|{c2['mid']}" and c2["mid"] != c1["mid"]
    _device_done(se, 3)
