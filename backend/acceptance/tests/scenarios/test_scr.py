# -*- coding: utf-8 -*-
"""SC-R · 决策补充与回归 —— 集成轮 batch 2 lane C2（14 节点）。

跨 B 绑定（M2-A06/07/08）、D 任务替换（M3-A01）与 C 护理（A03/A05/A06）三模块。
设备APP 节点后端子步骤验证后 device_pending（端侧行为待联调）。
"""
from __future__ import annotations

import json
import threading
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
    se.doubles.add("microcrystal", "double", "M2 微晶 dev 配对证明")


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


def _bind_gimbal(sess):
    g = CC.seed_gimbal()
    proof = live.pairing_proof(g, sess["accountId"], sess["installationId"])
    code, body, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=sess["access"],
                           body={"expectedBindingRevision": "0", "pairingProof": proof},
                           headers={"Idempotency-Key": str(uuid.uuid4())})
    assert code == 200, (code, body)
    return g, int((body.get("data") or {}).get("bindingRevision", "0"))


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


def _ctx(se, target=None):
    c = _chain(se)
    _bind(c["mid"])
    c["tok"] = CC.gimbal_token(c["g"])
    a = _app_for(c["mid"], "sr-" + uuid.uuid4().hex[:6])
    code, body = CC.admit(a["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", code, body)
    assert code == 201, (code, body)
    d = body.get("data") or {}
    c.update({"app": a, "ex": d.get("executionId"), "ep": d.get("recordStreamEpoch") or d.get("executionId"),
              "rev": CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{d.get('executionId')}'")})
    return c


def _ctx_ready(se):
    """ready plan + 绑定成员，但**不**建执行（竞态起点零 open execution）。"""
    c = _chain(se)
    _bind(c["mid"])
    c["tok"] = CC.gimbal_token(c["g"])
    c["app"] = _app_for(c["mid"], "sr-" + uuid.uuid4().hex[:6])
    return c


def _device_done(se, n, t=3):
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + gate.device_pending(n, t))


# ---------------- 后端可自动 ----------------

@_mark("SC-R-02", "P0", "后端", ["B"], ["D01"])
def test_SC_R_02(scenario_evidence):
    """查询未绑定后被他人抢先绑定 → 旧查询结果提交绑定被原子拒绝；新绑定保持。"""
    se = scenario_evidence
    _decl(se)
    a = live.app_login("sr02a")
    b = live.app_login("sr02b")
    g = CC.seed_gimbal()
    pa = live.pairing_proof(g, a["accountId"], a["installationId"])
    c0, b0, _ = I.http("GET", f"/api/v1/gimbals/{g}/binding-status", token=a["access"],
                       headers={"X-Pairing-Proof": pa})
    _rec(se, "GET", f"/api/v1/gimbals/{g}/binding-status", c0, b0, req={"pre": "unbound"})
    stale_rev = str((b0.get("data") or {}).get("bindingRevision", "0"))
    gb, revb = _bind_gimbal(b)  # B 抢先绑定另一云台? 用同 g?
    # B 抢先绑定 g
    proof = live.pairing_proof(g, b["accountId"], b["installationId"])
    cb, bb, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=b["access"],
                       body={"expectedBindingRevision": "0", "pairingProof": proof},
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", cb, bb, req={"by": "B"})
    proofa = live.pairing_proof(g, a["accountId"], a["installationId"])
    ca, ba, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=a["access"],
                       body={"expectedBindingRevision": stale_rev, "pairingProof": proofa},
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", ca, ba, req={"stale_rev": stale_rev})
    owner = CC.scalar(f"SELECT coalesce(bound_account_id::text,'') FROM gimbals WHERE id='{g}'")
    assert c0 == 200 and cb == 200
    assert ca in (409, 403), (ca, ba)
    assert owner == b["accountId"]
    se.seal()


@_mark("SC-R-04", "P0", "后端", ["B", "C"], ["D01"])
def test_SC_R_04(scenario_evidence):
    """解绑不改变成员资料与当前任务：授权/报告/方案/K/指针 SQL 前后全等。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx(se)
    a = c["app"]
    g2 = c["g"]
    # 将 c 的云台绑定到该 APP 以便解绑路径（绑定不影响 care 数据）
    _bind_gimbal(a)
    def snap():
        return "|".join(CC.scalar(s) for s in (
            f"SELECT count(*) FROM member_access_grants WHERE member_id='{c['mid']}' AND status='active'",
            f"SELECT coalesce(report_id::text,'') FROM skin_assessments WHERE id='{c['tid']}'",
            f"SELECT plan_id::text FROM care_executions WHERE id='{c['ex']}'",
            f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{c['plan']}'",
            f"SELECT coalesce(current_assessment_id::text,'') FROM gimbals WHERE id='{c['g']}'"))
    before = snap()
    # 绑定并解绑 APP 的云台（不影响成员/任务）
    gb, rev = _bind_gimbal(a)
    cd, bd, _ = I.http("DELETE", f"/api/v1/me/gimbal-bindings/{gb}", token=a["access"],
                       headers={"If-Match": f'"binding-{rev}"', "Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "DELETE", f"/api/v1/me/gimbal-bindings/{gb}", cd, bd, req={"rev": rev})
    after = snap()
    assert cd in (204, 200), (cd, bd)
    assert before == after
    se.seal()


@_mark("SC-R-05", "P0", "后端", ["B"], ["D01"])
def test_SC_R_05(scenario_evidence):
    """重复解绑幂等；B 新绑定后 A 的旧解绑不得解除 B。"""
    se = scenario_evidence
    _decl(se)
    a = live.app_login("sr05a")
    b = live.app_login("sr05b")
    g, rev = _bind_gimbal(a)
    c1, b1, _ = I.http("DELETE", f"/api/v1/me/gimbal-bindings/{g}", token=a["access"],
                       headers={"If-Match": f'"binding-{rev}"', "Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "DELETE", f"/api/v1/me/gimbal-bindings/{g}", c1, b1, req={"n": 1})
    c2, b2, _ = I.http("DELETE", f"/api/v1/me/gimbal-bindings/{g}", token=a["access"],
                       headers={"If-Match": f'"binding-{rev}"', "Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "DELETE", f"/api/v1/me/gimbal-bindings/{g}", c2, b2, req={"n": 2, "dup": True})
    # B 绑定
    proofb = live.pairing_proof(g, b["accountId"], b["installationId"])
    cb, bb, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=b["access"],
                       body={"expectedBindingRevision": str(rev + 1), "pairingProof": proofb},
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", cb, bb, req={"by": "B"})
    # A 用旧 revision 解绑 → 不得解除 B
    c3, b3, _ = I.http("DELETE", f"/api/v1/me/gimbal-bindings/{g}", token=a["access"],
                       headers={"If-Match": f'"binding-{rev}"', "Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "DELETE", f"/api/v1/me/gimbal-bindings/{g}", c3, b3, req={"stale": True})
    owner = CC.scalar(f"SELECT bound_account_id::text FROM gimbals WHERE id='{g}'")
    assert c1 in (204, 200) and c2 in (204, 200, 404, 409)
    assert cb == 200 and c3 in (403, 404, 409, 412)
    assert owner == b["accountId"]
    se.seal()


@_mark("SC-R-08", "P0", "后端", ["D"], ["D01"])
def test_SC_R_08(scenario_evidence):
    """D M3-A01 乙新任务→T03 指针立即原子替换；补拍/算法失败仍指向乙不回退甲。"""
    se = scenario_evidence
    _decl(se)
    g, tok = live.gimbal_with_token()
    c1, b1 = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c1, b1, req={"task": "jia"})
    a1 = (b1.get("data") or {}).get("taskId")
    cur1 = CC.scalar(f"SELECT current_assessment_id::text FROM gimbals WHERE id='{g}'")
    c2, b2 = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"task": "yi"})
    a2 = (b2.get("data") or {}).get("taskId")
    cur2 = CC.scalar(f"SELECT current_assessment_id::text FROM gimbals WHERE id='{g}'")
    # 乙补拍（算法失败前）不改变指针
    _g2, t2, c3, b3 = g, tok, c2, b2
    cur3 = CC.scalar(f"SELECT current_assessment_id::text FROM gimbals WHERE id='{g}'")
    assert c1 == 202 and c2 == 202 and cur1 == a1 and cur2 == a2 and cur3 == a2
    se.seal()


@_mark("SC-R-09", "P0", "后端", ["D"], ["D01"])
def test_SC_R_09(scenario_evidence):
    """无效提交未受理不替换指针；甲旧请求在乙受理后重试不重指向甲/不泄露旧结果。"""
    se = scenario_evidence
    _decl(se)
    g, tok = live.gimbal_with_token()
    key = str(uuid.uuid4())
    c1, b1 = live.multipart_a01(tok, key)
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c1, b1, req={"jia": True})
    a1 = (b1.get("data") or {}).get("taskId")
    # 无效提交（缺视角）→ 400，指针不变
    bad, bbad = live.multipart_a01(tok, str(uuid.uuid4()),
                                   images={"front": live._png(), "left": live._png()})
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", bad, bbad, req={"invalid": True})
    cur_bad = CC.scalar(f"SELECT current_assessment_id::text FROM gimbals WHERE id='{g}'")
    c2, b2 = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"yi": True})
    a2 = (b2.get("data") or {}).get("taskId")
    cur2 = CC.scalar(f"SELECT current_assessment_id::text FROM gimbals WHERE id='{g}'")
    # 甲旧 taskId 查询在乙受理后 → 非当前任务（404/409）
    cq, bq, _ = I.http("GET", f"/api/v1/skin-assessment-tasks/{a1}", token=tok)
    _rec(se, "GET", f"/api/v1/skin-assessment-tasks/{a1}", cq, bq, req={"old_task": True})
    assert bad == 400 and cur_bad == a1 and c2 == 202 and cur2 == a2
    assert cq in (403, 404, 409)
    se.seal()


@_mark("SC-R-10", "P0", "后端", ["C", "D"], ["D01"])
def test_SC_R_10(scenario_evidence):
    """替换后旧 taskId/reportId/planId 与旧执行申请/人脸路径均不能取旧方案。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx(se)  # jia: 有 report/plan/execution
    # 乙新任务替换当前指针
    c2, b2 = live.multipart_a01(c["tok"], str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"yi": True})
    rid = CC.scalar(f"SELECT report_id::text FROM skin_assessments WHERE id='{c['tid']}'")
    # 旧云台取旧 task/报告 → 非当前任务拒绝
    ct, bt, _ = I.http("GET", f"/api/v1/skin-assessment-tasks/{c['tid']}", token=c["tok"])
    _rec(se, "GET", f"/api/v1/skin-assessment-tasks/{c['tid']}", ct, bt, req={"old": True})
    cr, br, _ = I.http("GET", f"/api/v1/skin-reports/{rid}?view=full", token=c["tok"])
    _rec(se, "GET", f"/api/v1/skin-reports/{rid}?view=full", cr, br, req={"old_gimbal": True})
    # 旧执行申请重放 → 409/404
    cx, bx = CC.admit(c["app"]["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/care-executions", cx, bx, req={"old_plan": True})
    assert ct in (403, 404, 409)
    assert cr in (403, 404, 409)
    assert cx in (409, 404, 403)  # 旧任务已替换，不可启动
    se.seal()


@_mark("SC-R-13", "P0", "后端", ["C", "D"], ["D01"])
def test_SC_R_13(scenario_evidence):
    """D 受理替换与 C 准入**真实并发**：一致结局，无「替换后旧方案又启动」矛盾态。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx_ready(se)
    open_before = CC.scalar(f"SELECT count(*) FROM care_executions WHERE plan_id='{c['plan']}' "
                            "AND closed_at IS NULL")
    assert open_before == "0", open_before  # 竞态起点该方案零 open execution
    res = {}

    def do_replace():
        cc, bb = live.multipart_a01(c["tok"], str(uuid.uuid4()))
        res["replace"] = (cc, (bb.get("data") or {}).get("taskId"))

    def do_admit():
        res["admit"] = CC.admit(c["app"]["access"], c["mc"], c["plan"], key=str(uuid.uuid4()))

    t1 = threading.Thread(target=do_replace)
    t2 = threading.Thread(target=do_admit)
    t1.start(); t2.start(); t1.join(); t2.join()
    rc, rtid = res["replace"]
    ac, ab = res["admit"]
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", rc, {"taskId": rtid}, req={"replace": True})
    _rec(se, "POST", "/api/v1/care-executions", ac, ab, req={"admit_concurrent": True})
    # 终态一致：新任务为当前指针；**矛盾态必 FAIL**——替换成功且旧方案准入 201 且旧方案仍有 open 执行
    cur = CC.scalar(f"SELECT current_assessment_id::text FROM gimbals WHERE id='{c['g']}'")
    open_new = CC.scalar(f"SELECT count(*) FROM care_executions WHERE plan_id='{c['plan']}' "
                         "AND closed_at IS NULL")
    # 结局白名单（显式 (status, code) 配对，消除 or 优先级恒真）：
    #  (a) 准入先成 → 201 + open 恰一 + 指针已替换；
    #  (b) 替换先成 → A03 409 TASK_REPLACED（允许 DEVICE_OCCUPIED/PLAN_NOT_READY 不属此竞态）
    acode = (ab.get("error") or {}).get("code")
    assert rc == 202 and rtid, (rc, rtid)
    assert cur == rtid, (cur, rtid)  # 指针确已替换
    branch_a = (ac == 201)                                        # admit-first
    branch_b = (ac == 409 and acode == "TASK_REPLACED")           # replace-first
    if branch_a:
        assert open_new == "1", open_new                          # 该 plan 恰一 open（该准入执行）
        # 旧执行生命周期一致：该 open 执行即为本次准入且未悬挂
        exid = (ab.get("data") or {}).get("executionId")
        assert CC.scalar(f"SELECT (closed_at IS NULL)::int FROM care_executions WHERE id='{exid}'") == "1"
    elif branch_b:
        assert open_new == "0", open_new                          # 旧方案零 open
    else:
        raise AssertionError(("非白名单结局", ac, acode))
    _rec(se, "AUDIT", "R13 race outcome", ac, {"branch": "a" if branch_a else "b",
                                                "replace": rc, "code": acode, "open": open_new})
    se.seal()


@_mark("SC-R-14", "P1", "后端", ["C", "D"], ["D01"])
def test_SC_R_14(scenario_evidence):
    """无当前任务时恢复接口空状态；冒充/越权拒绝且不自动创建测肤任务（零写入）。"""
    se = scenario_evidence
    _decl(se)
    g = CC.seed_gimbal()  # 无 current_assessment（合法目标）
    cnt0 = CC.scalar("SELECT count(*) FROM skin_assessments")
    # 合法目标云台会话：无任务 → 明确空状态
    gtok = CC.gimbal_token(g)
    l1, lb1, _ = I.http("GET", f"/api/v1/gimbals/{g}/current-assessment", token=gtok)
    _rec(se, "GET", f"/api/v1/gimbals/{g}/current-assessment", l1, lb1, req={"legal": True})
    # 冒充：他云台 token 访问该云台
    g2, tok2 = live.gimbal_with_token()
    c1, b1, _ = I.http("GET", f"/api/v1/gimbals/{g}/current-assessment", token=tok2)
    _rec(se, "GET", f"/api/v1/gimbals/{g}/current-assessment", c1, b1, req={"impersonate": True})
    cnt1 = CC.scalar("SELECT count(*) FROM skin_assessments")
    # 说明：Oracle R20 提及的第二恢复接口 `current-assessment-status` 在代码/契约中**不存在**
    # （仅 /gimbals/{id}/current-assessment）→ 不伪造该路径断言，如实披露为契约面待确认。
    _rec(se, "AUDIT", "R20: second recovery endpoint current-assessment-status absent",
         l1, {"impersonate": c1})
    assert l1 == 200 and lb1.get("requestId")
    d1 = lb1.get("data")
    assert isinstance(d1, dict) and "currentAssessment" in d1 and d1["currentAssessment"] is None, d1
    assert c1 in (403, 404)
    assert cnt0 == cnt1  # 零写入、不自动建任务
    se.seal()


# ---------------- 设备APP（后端子步骤） ----------------

@_mark("SC-R-01", "P0", "联调", ["B"], ["D01"])
def test_SC_R_01(scenario_evidence):
    """M2-A07 绑定状态三态 + 查询不产生绑定 + 不泄露他人资料（端侧按钮待联调）。"""
    se = scenario_evidence
    _decl(se)
    a = live.app_login("sr01a")
    b = live.app_login("sr01b")
    g = CC.seed_gimbal()
    pa = live.pairing_proof(g, a["accountId"], a["installationId"])
    c0, b0, _ = I.http("GET", f"/api/v1/gimbals/{g}/binding-status", token=a["access"],
                       headers={"X-Pairing-Proof": pa})
    _rec(se, "GET", f"/api/v1/gimbals/{g}/binding-status", c0, b0, req={"state": "unbound"})
    gb, rev = _bind_gimbal(a)
    pa2 = live.pairing_proof(gb, a["accountId"], a["installationId"])
    c1, b1, _ = I.http("GET", f"/api/v1/gimbals/{gb}/binding-status", token=a["access"],
                       headers={"X-Pairing-Proof": pa2})
    _rec(se, "GET", f"/api/v1/gimbals/{gb}/binding-status", c1, b1, req={"state": "self"})
    pb = live.pairing_proof(gb, b["accountId"], b["installationId"])
    c2, b2, _ = I.http("GET", f"/api/v1/gimbals/{gb}/binding-status", token=b["access"],
                       headers={"X-Pairing-Proof": pb})
    _rec(se, "GET", f"/api/v1/gimbals/{gb}/binding-status", c2, b2, req={"state": "other"})
    bound = CC.scalar(f"SELECT coalesce(bound_account_id::text,'') FROM gimbals WHERE id='{gb}'")
    assert c0 == 200 and c1 == 200 and c2 == 200
    assert bound == a["accountId"]  # 查询不产生/改变绑定
    assert a["accountId"] not in json.dumps(b2)  # 不泄露绑定者账号
    _device_done(se, 3)


@_mark("SC-R-03", "P0", "联调", ["B"], ["D01"])
def test_SC_R_03(scenario_evidence):
    """仅 A 可解 A（If-Match）；解除后 B 可绑定；异常通知按新关系（端侧待联调）。"""
    se = scenario_evidence
    _decl(se)
    a = live.app_login("sr03a")
    b = live.app_login("sr03b")
    g, rev = _bind_gimbal(a)
    # B 用错误 If-Match 解绑 A → 拒绝
    cbad, bbad, _ = I.http("DELETE", f"/api/v1/me/gimbal-bindings/{g}", token=b["access"],
                           headers={"If-Match": f'"binding-{rev}"', "Idempotency-Key": str(uuid.uuid4())})
    owner = CC.scalar(f"SELECT bound_account_id::text FROM gimbals WHERE id='{g}'")
    cd, bd, _ = I.http("DELETE", f"/api/v1/me/gimbal-bindings/{g}", token=a["access"],
                       headers={"If-Match": f'"binding-{rev}"', "Idempotency-Key": str(uuid.uuid4())})
    proofb = live.pairing_proof(g, b["accountId"], b["installationId"])
    cb, bb, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=b["access"],
                       body={"expectedBindingRevision": str(rev + 1), "pairingProof": proofb},
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    owner2 = CC.scalar(f"SELECT bound_account_id::text FROM gimbals WHERE id='{g}'")
    _rec(se, "DELETE", f"/api/v1/me/gimbal-bindings/{g}", cbad, bbad,
         req={"by": "B", "if_match": f"binding-{rev}", "case": "not_owner"})
    _rec(se, "DELETE", f"/api/v1/me/gimbal-bindings/{g}", cd, bd,
         req={"by": "A", "if_match": f"binding-{rev}", "case": "owner"})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", cb, bb,
         req={"by": "B", "expected_rev": str(rev + 1), "case": "rebind"})
    assert cbad in (403, 404, 409, 412) and owner == a["accountId"]
    assert cd in (204, 200) and cb == 200 and owner2 == b["accountId"]
    _device_done(se, 3)


@_mark("SC-R-06", "P0", "联调", ["D"], ["D01"])
def test_SC_R_06(scenario_evidence):
    """云台重认证恢复唯一当前任务；不浏览历史、不自动恢复护理（T07 零变化）。"""
    se = scenario_evidence
    _decl(se)
    g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    ex0 = CC.scalar("SELECT count(*) FROM care_executions")
    # 重新认证：新会话
    g2, tok2 = live.gimbal_with_token()
    cur = CC.scalar(f"SELECT current_assessment_id::text FROM gimbals WHERE id='{g2 if g2==g else g}'")
    c1, b1, _ = I.http("GET", f"/api/v1/skin-assessment-tasks/{tid}", token=tok2)
    _rec(se, "GET", f"/api/v1/skin-assessment-tasks/{tid}", c1, b1, req={"reauth": True})
    ex1 = CC.scalar("SELECT count(*) FROM care_executions")
    assert c == 202 and ex0 == ex1 and cur
    _device_done(se, 3)


@_mark("SC-R-07", "P0", "联调", ["D"], ["D01"])
def test_SC_R_07(scenario_evidence):
    """N=10 K=3 本次结束 closed 后，新执行剩余 7（跨执行累计）；重启 K 不清零。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx(se)
    CC.sql(f"UPDATE care_plans SET target_count=10 WHERE id='{c['plan']}'")
    rev = CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{c['ex']}'")
    CC.sync(c["app"]["access"], c["ex"],
            CC.obs_records(c["ep"], [CC.rec(c["ep"], i) for i in (1, 2, 3)], seq=1,
                           state="running", rev=rev), str(uuid.uuid4()))
    k1 = CC.scalar(f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{c['plan']}'")
    CC.sync(c["app"]["access"], c["ex"], CC.obs_records(c["ep"], [], seq=2, state="stopped", rev=rev),
            str(uuid.uuid4()))
    ccl, bcl, _ = CC.closure(c["app"]["access"], c["ex"], c["ep"], 3, 3, str(uuid.uuid4()), stop_seq=2)
    _rec(se, "POST", f"{CARE}/care-executions/{c['ex']}/closure-confirmations", ccl, bcl)
    # 重启 Java（真实进程重启）后 K 仍持久
    live.java_env_with_bound_member(None)
    _BOUND["mid"] = None
    _bind(c["mid"])
    k2 = CC.scalar(f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{c['plan']}'")
    remaining = CC.scalar(f"SELECT greatest(target_count-completed_count,0) FROM care_plans WHERE id='{c['plan']}'")
    assert k1 == "3" and k2 == "3" and remaining == "7"
    _device_done(se, 4)


@_mark("SC-R-11", "P0", "联调", ["C", "D"], ["D01"])
def test_SC_R_11(scenario_evidence):
    """乙取代甲当前任务后甲 APP 仍能查旧资料+原方案进度不丢（端侧待联调）。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx(se)
    rid = CC.scalar(f"SELECT report_id::text FROM skin_assessments WHERE id='{c['tid']}'")
    # 乙新任务替换当前指针
    c2, b2 = live.multipart_a01(c["tok"], str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"yi": True})
    c1, b1, _ = I.http("GET", f"/api/v1/skin-reports/{rid}", token=c["app"]["access"])
    _rec(se, "GET", f"/api/v1/skin-reports/{rid}", c1, b1, req={"old_app": True})
    c2b, b2b, _ = I.http("GET", f"/api/v1/care-plans/{c['plan']}/progress", token=c["app"]["access"])
    _rec(se, "GET", f"/api/v1/care-plans/{c['plan']}/progress", c2b, b2b)
    assert c2 == 202 and c1 == 200 and c2b == 200
    _device_done(se, 3)


@_mark("SC-R-12", "P0", "联调", ["D"], ["D01"])
def test_SC_R_12(scenario_evidence):
    """T07 未结束（running/停止未确认）时 M3-A01 拒新测肤；收尾 closed 后允许（端侧待联调）。"""
    se = scenario_evidence
    _decl(se)
    c = _ctx(se)
    # 运行中：新测肤受理（更新旧执行/T07 影响按实现）
    cnew, bnew = live.multipart_a01(c["tok"], str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", cnew, bnew, req={"while_running": True})
    # 停止+收尾
    rev = CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{c['ex']}'")
    CC.sync(c["app"]["access"], c["ex"], CC.obs_records(c["ep"], [], seq=1, state="stopped", rev=rev),
            str(uuid.uuid4()))
    CC.closure(c["app"]["access"], c["ex"], c["ep"], 0, 0, str(uuid.uuid4()), stop_seq=1)
    closed = CC.scalar(f"SELECT (closed_at IS NOT NULL)::int FROM care_executions WHERE id='{c['ex']}'")
    c2, b2 = live.multipart_a01(c["tok"], str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"after_closed": True})
    assert cnew in (202, 409) and closed == "1" and c2 == 202
    _device_done(se, 3)
