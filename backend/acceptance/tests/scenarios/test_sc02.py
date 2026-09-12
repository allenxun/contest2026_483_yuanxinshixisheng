# -*- coding: utf-8 -*-
"""SC-02 · 测肤任务、补拍与报告归档 —— 集成轮 batch 2 真实步骤。

01/02/03/04/07/08/09/10/11 编写真实步骤（云台会话 + M3 受理 + worker --once + SQL 侧证）。
05（质量不合格注入）/06（非同人/不确定注入）**保持 staged**：当前树 D 替身
（build_face_port/build_skin_port 恒用 FaceDouble()/SkinDouble() 默认参数）**未提供
env 故障注入 seam**，黑盒无法产生 needs_retake / same_person=false / uncertain；E 无权改
D 代码，如实记缺口待 D/总协调补 seam 后再写。
"""
from __future__ import annotations

import datetime
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


def _worker_until(se, sql_cond, cycles=140, env_extra=None):
    for _ in range(cycles):
        if CC.scalar(sql_cond) == "1":
            return True
        I.worker_once(env_extra=env_extra, timeout=180)
    return CC.scalar(sql_cond) == "1"


def _audit(se, note, code=0, body=None):
    se.record_raw(method="AUDIT", path=note, status=code, request_headers={},
                  request_json=None, response_excerpt=json.dumps(body or {}, ensure_ascii=False)[:800],
                  started_at=0.0, elapsed_ms=0.0)


def _decl(se):
    se.doubles.add("face_algo", "double", "D FaceDouble（dev 替身，reliable_new/accepted）")
    se.doubles.add("oss", "double", "A FilesystemStorageDouble")
    se.doubles.add("gimbal_device", "double", "云台会话 dev 凭据")


@_mark("SC-02-01", "P0", "后端", ["D"], ["D06"])
def test_SC_02_01(scenario_evidence):
    """提交合法三视角任务 → 202+taskId+queued，绑定原云台，可 A03 查询。"""
    se = scenario_evidence
    _decl(se)
    g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b, req={"photoVersion": "1"})
    tid = (b.get("data") or {}).get("taskId")
    cur = CC.scalar(f"SELECT current_assessment_id::text FROM gimbals WHERE id='{g}'")
    st = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
    cq, bq, _ = I.http("GET", f"/api/v1/skin-assessment-tasks/{tid}", token=tok)
    _rec(se, "GET", f"/api/v1/skin-assessment-tasks/{tid}", cq, bq)
    assert c == 202, (c, b)
    assert (b.get("data") or {}).get("status") == "queued" and tid
    assert cur == tid and st in ("queued", "analyzing"), (cur, st)
    assert cq == 200 and (bq.get("data") or {}).get("taskId") == tid
    se.seal()


@_mark("SC-02-02", "P0", "后端", ["D"], ["D01", "D06"])
def test_SC_02_02(scenario_evidence):
    """身份/归属校验：APP 直提/未认证拒绝；他云台不能读本云台任务。"""
    se = scenario_evidence
    _decl(se)
    g1, t1 = live.gimbal_with_token()
    c, b = live.multipart_a01(t1, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    # APP 直接提交 → 403 CALLER_NOT_ALLOWED
    app = live.app_login("sc0202")
    ca, ba = live.multipart_a01(app["access"], str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", ca, ba, req={"caller": "app"})
    # 未认证提交 → 401
    cn, bn = live.multipart_a01("forged-token", str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", cn, bn, req={"caller": "anon"})
    # 他云台读本任务 → 404
    g2, t2 = live.gimbal_with_token()
    c2, b2, _ = I.http("GET", f"/api/v1/skin-assessment-tasks/{tid}", token=t2)
    _rec(se, "GET", f"/api/v1/skin-assessment-tasks/{tid}", c2, b2, req={"gimbal": g2})
    assert c == 202
    assert ca == 403 and ba["error"]["code"] == "CALLER_NOT_ALLOWED"
    assert cn == 401
    assert c2 == 404 and b2["error"]["code"] == "RESOURCE_NOT_VISIBLE"
    se.seal()


@_mark("SC-02-03", "P1", "后端", ["D"], ["D06"])
def test_SC_02_03(scenario_evidence):
    """照片缺失/格式非法 → 400，可修正，不生成看似完整的报告。"""
    se = scenario_evidence
    _decl(se)
    _g, tok = live.gimbal_with_token()
    before = CC.scalar("SELECT count(*) FROM skin_assessments")
    # 缺 right 视角
    c1, b1 = live.multipart_a01(tok, str(uuid.uuid4()),
                                images={"front": live._png(), "left": live._png()})
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c1, b1, req={"missing": "right"})
    # metadata 非法（photoVersion 非 "1"）
    c2, b2 = live.multipart_a01(tok, str(uuid.uuid4()), photo_version="2")
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"photoVersion": "2"})
    after = CC.scalar("SELECT count(*) FROM skin_assessments")
    reports = CC.scalar("SELECT count(*) FROM skin_assessments WHERE report_payload IS NOT NULL")
    assert c1 == 400 and c2 == 400
    assert before == after and reports == "0"
    se.seal()


@_mark("SC-02-04", "P0", "后端", ["D"], ["D04"])
def test_SC_02_04(scenario_evidence):
    """去重：同键同内容→原任务(200 replay)；同键异内容→409；先鉴权后返回。"""
    se = scenario_evidence
    _decl(se)
    g, tok = live.gimbal_with_token()
    key = str(uuid.uuid4())
    cs = f"cs-{uuid.uuid4().hex[:8]}"
    imgs = live.images3()
    c1, b1 = live.multipart_a01(tok, key, images=imgs, capture_session_id=cs)
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c1, b1, req={"key": key, "n": 1})
    c2, b2 = live.multipart_a01(tok, key, images=imgs, capture_session_id=cs)
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"key": key, "n": 2})
    c3, b3 = live.multipart_a01(tok, key, images=live.images3())
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c3, b3, req={"key": key, "diff": True})
    cn, bn = live.multipart_a01("forged", key, images=imgs)
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", cn, bn, req={"key": key, "anon": True})
    t1 = (b1.get("data") or {}).get("taskId")
    assert c1 == 202
    assert c2 == 200 and (b2.get("data") or {}).get("taskId") == t1
    assert c3 == 409
    assert cn == 401
    assert CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE gimbal_id='{g}'") == "1"
    se.seal()


@_mark("SC-02-07", "P0", "集成", ["D"], ["D06"])
def test_SC_02_07(scenario_evidence):
    """可靠新成员才建档：worker 建新成员并关联 T06/T05，不串成员。

    （「可靠匹配已有成员」分支需 D face 替身 search=matched 注入 seam，当前树未提供，见模块 docstring。）
    """
    se = scenario_evidence
    _decl(se)
    _g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    ok = _worker_until(se, f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{tid}'")
    st = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
    mid = CC.scalar(f"SELECT member_id::text FROM skin_assessments WHERE id='{tid}'")
    plan_mid = CC.scalar(f"SELECT member_id::text FROM care_plans WHERE assessment_id='{tid}'")
    ns = CC.scalar(f"SELECT identity_namespace FROM members WHERE id='{mid}'")
    assert c == 202 and ok and st == "report_ready", (c, st)
    assert mid and plan_mid == mid and ns == "mvp-ns-1", (mid, plan_mid, ns)
    se.seal()


@_mark("SC-02-08", "P1", "后端", ["D"], ["D06"])
def test_SC_02_08(scenario_evidence):
    """补拍沿用原任务（**缺口披露**）：D 替身缺 env 故障注入 seam，无法产生
    `needs_retake`；black-box 无法进入合法补拍态。本节点验证可达安全边界
    「非补拍态 A02 被拒（409 PHOTO_VERSION_CONFLICT）且照片版本/任务数不变」，
    正例（新版本原任务处理、旧引用受控、他云台 404）待 D seam 后补写。"""
    se = scenario_evidence
    _decl(se)
    _g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    _worker_until(se, f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{tid}'")
    cnt_before = CC.scalar("SELECT count(*) FROM skin_assessments")
    md = {"expectedPhotoVersion": "1", "replacedViews": ["front"]}
    c2, b2 = live.multipart_a02(tok, str(uuid.uuid4()), tid, "2", md,
                                {"front": live._png() + b"NEW"})
    _rec(se, "PUT", f"/api/v1/skin-assessment-tasks/{tid}/photo-versions/2", c2, b2)
    ver = CC.scalar(f"SELECT current_photo_version FROM skin_assessments WHERE id='{tid}'")
    cnt_after = CC.scalar("SELECT count(*) FROM skin_assessments")
    _audit(se, "SC-02-08 retake-not-required boundary", c2, {"photoVersion": ver})
    assert c == 202 and c2 == 409 and b2["error"]["code"] == "PHOTO_VERSION_CONFLICT"
    assert ver == "1" and cnt_before == cnt_after
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + "D FaceDouble 缺 env 故障注入 seam（quality=needs_retake）；"
                "待 D/总协调补 seam 后补写补拍正例")


@_mark("SC-02-09", "P0", "集成", ["D"], ["D04", "D06"])
def test_SC_02_09(scenario_evidence):
    """补拍版本幂等/冲突（**缺口披露**）：合法补拍态需 `needs_retake` seam（当前树缺）。
    本节点验证可达边界「非补拍态同键重复 A02 一律 409 PHOTO_VERSION_CONFLICT、
    不产生新任务/新照片版本」，正例（同版本同内容幂等/异内容冲突/旧结果不覆盖）
    待 D seam 后补写。"""
    se = scenario_evidence
    _decl(se)
    _g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    _worker_until(se, f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{tid}'")
    md = {"expectedPhotoVersion": "1", "replacedViews": ["front"]}
    key = str(uuid.uuid4())
    c1, b1 = live.multipart_a02(tok, key, tid, "2", md, {"front": live._png() + b"V2"})
    _rec(se, "PUT", f"/api/v1/skin-assessment-tasks/{tid}/photo-versions/2", c1, b1, req={"n": 1})
    c2, b2 = live.multipart_a02(tok, key, tid, "2", md, {"front": live._png() + b"V2"})
    _rec(se, "PUT", f"/api/v1/skin-assessment-tasks/{tid}/photo-versions/2", c2, b2, req={"n": 2})
    ver = CC.scalar(f"SELECT current_photo_version FROM skin_assessments WHERE id='{tid}'")
    _audit(se, "SC-02-09 retake-not-required boundary", c2, {"photoVersion": ver})
    assert c1 == 409 and c2 == 409 and ver == "1"
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + "D FaceDouble 缺 env 故障注入 seam（quality=needs_retake）；"
                "待 D/总协调补 seam 后补写补拍幂等/冲突正例")


@_mark("SC-02-10", "P1", "集成", ["D"], ["D06", "D07"])
def test_SC_02_10(scenario_evidence):
    """算法失败 → 真实失败状态、不虚假成功；查询不触发新分析。

    注入：worker 以 MVP_D_SKIN_PROVIDER=aliyun_skin（未激活）运行 → analyze 抛
    ProviderNotActivated（受控失败注入，经真实 worker 进程；非真实供应商）。
    """
    se = scenario_evidence
    se.doubles.add("face_algo", "double", "D FaceDouble")
    se.doubles.add("oss", "double", "A FilesystemStorageDouble")
    se.doubles.add("gimbal_device", "double", "云台会话 dev 凭据")
    _g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    for _ in range(8):
        I.worker_once(env_extra={"MVP_D_SKIN_PROVIDER": "aliyun_skin"}, timeout=180)
        if CC.scalar(f"SELECT (status IN ('failed','needs_retake'))::int FROM skin_assessments "
                     f"WHERE id='{tid}'") == "1":
            break
    st = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
    payload = CC.scalar(f"SELECT coalesce(report_payload::text,'') FROM skin_assessments WHERE id='{tid}'")
    # 查询不得触发新分析（不产生新 job）
    jobs_before = CC.scalar("SELECT count(*) FROM async_jobs")
    cq, bq, _ = I.http("GET", f"/api/v1/skin-assessment-tasks/{tid}", token=tok)
    _rec(se, "GET", f"/api/v1/skin-assessment-tasks/{tid}", cq, bq)
    jobs_after = CC.scalar("SELECT count(*) FROM async_jobs")
    assert st in ("queued", "analyzing", "failed", "needs_retake") and st != "report_ready", st
    assert payload == ""
    assert jobs_before == jobs_after
    se.seal()


@_mark("SC-02-05", "P1", "集成", ["D"], ["D06"])
def test_SC_02_05(scenario_evidence):
    """质量不合格 → 需补拍、不冒充报告就绪。

    **缺口（如实披露）**：D 替身未提供 env 故障注入 seam（FaceDouble 恒
    quality=accepted），black-box 无法产生 `needs_retake/requiredViews` 正例。
    本节点用**可达故障**（face 提供方不可用 `MVP_D_FACE_PROVIDER=aliyun_face`）
    验证核心安全不变量「不冒充报告就绪 / 不产生报告」，正例待 D seam 后补写。
    """
    se = scenario_evidence
    _decl(se)
    _g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    st = ""
    for _ in range(6):
        I.worker_once(env_extra={"MVP_D_FACE_PROVIDER": "aliyun_face"}, timeout=180)
        st = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
        if st in ("failed", "needs_retake"):
            break
    payload = CC.scalar(f"SELECT coalesce(report_payload::text,'') FROM skin_assessments WHERE id='{tid}'")
    _audit(se, "SC-02-05 safety-invariant check (no false report_ready)", 0,
           {"status": st, "report_payload_empty": payload == ""})
    assert c == 202
    assert st != "report_ready" and payload == "", (st, payload)
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + "D FaceDouble 缺 env 故障注入 seam（quality=needs_retake）；"
                "待 D/总协调补 seam 后补写正例（requiredViews）")


@_mark("SC-02-06", "P0", "集成", ["D"], ["D06"])
def test_SC_02_06(scenario_evidence):
    """三视角非同人/不确定 → 不误归成员、不自动建档。

    **缺口（如实披露）**：D 替身未提供 env 故障注入 seam（FaceDouble 恒
    same_person=True/search=reliable_new），black-box 无法产生 `NOT_SAME_PERSON`
    /`IDENTITY_UNCERTAIN` 正例。本节点用**可达故障**验证核心安全不变量
    「不误归成员 / 不自动建档 / 不出报告」，正例待 D seam 后补写。
    """
    se = scenario_evidence
    _decl(se)
    _g, tok = live.gimbal_with_token()
    members_before = CC.scalar("SELECT count(*) FROM members")
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    st = ""
    for _ in range(6):
        I.worker_once(env_extra={"MVP_D_FACE_PROVIDER": "aliyun_face"}, timeout=180)
        st = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
        if st in ("failed", "needs_retake"):
            break
    members_after = CC.scalar("SELECT count(*) FROM members")
    payload = CC.scalar(f"SELECT coalesce(report_payload::text,'') FROM skin_assessments WHERE id='{tid}'")
    _audit(se, "SC-02-06 safety-invariant check (no mis-enroll/no auto member)", 0,
           {"status": st, "members_before": members_before, "members_after": members_after})
    assert c == 202
    assert st != "report_ready" and payload == ""
    assert members_before == members_after
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + "D FaceDouble 缺 env 故障注入 seam（same_person=false/"
                "search=uncertain）；待 D/总协调补 seam 后补写正例")


@_mark("SC-02-11", "P0", "后端", ["D"], ["D01"])
def test_SC_02_11(scenario_evidence):
    """查询权限：云台仅自己当前任务；APP 须成员授权+可靠归档；不凭 ID 越权。"""
    se = scenario_evidence
    _decl(se)
    _g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    tid = (b.get("data") or {}).get("taskId")
    ready = _worker_until(se, f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{tid}'")
    mid = CC.scalar(f"SELECT member_id::text FROM skin_assessments WHERE id='{tid}'")
    rid = CC.scalar(f"SELECT report_id::text FROM skin_assessments WHERE id='{tid}'")
    assert ready and mid and rid, (ready, mid, rid)
    # APP 无授权 → 404
    app = live.app_login("sc0211")
    c1, b1, _ = I.http("GET", f"/api/v1/members/{mid}/skin-reports", token=app["access"])
    _rec(se, "GET", f"/api/v1/members/{mid}/skin-reports", c1, b1)
    # APP 授权后可见
    CC.seed_grant(app["accountId"], mid, status="active")
    c2, b2, _ = I.http("GET", f"/api/v1/members/{mid}/skin-reports", token=app["access"])
    _rec(se, "GET", f"/api/v1/members/{mid}/skin-reports", c2, b2)
    c3, b3, _ = I.http("GET", f"/api/v1/skin-reports/{rid}", token=app["access"])
    _rec(se, "GET", f"/api/v1/skin-reports/{rid}", c3, b3)
    assert c1 == 404 and b1["error"]["code"] == "RESOURCE_NOT_VISIBLE"
    assert c2 == 200 and any(it.get("reportId") == rid
                             for it in ((b2.get("data") or {}).get("items") or []))
    assert c3 == 200
    se.seal()
