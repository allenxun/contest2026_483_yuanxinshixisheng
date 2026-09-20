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
import time
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
    before = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE gimbal_id='{_g}'")
    # 缺 right 视角
    c1, b1 = live.multipart_a01(tok, str(uuid.uuid4()),
                                images={"front": live._png(), "left": live._png()})
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c1, b1, req={"missing": "right"})
    # metadata 非法（photoVersion 非 "1"）
    c2, b2 = live.multipart_a01(tok, str(uuid.uuid4()), photo_version="2")
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"photoVersion": "2"})
    after = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE gimbal_id='{_g}'")
    reports = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE gimbal_id='{_g}' AND report_payload IS NOT NULL")
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
    """补拍正例：needs_retake 进入补拍态 → 同 taskId 新版本 v2 成功推进；跨云台拒绝零写入；
    旧照片引用受控（v1 front 保留但当前版本引用已替换为新 media）。"""
    se = scenario_evidence
    _decl(se)
    _g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b, req={"inject": "needs_retake"})
    tid = (b.get("data") or {}).get("taskId")
    assert c == 202 and tid, (c, b)
    for _ in range(6):
        I.worker_once(env_extra={"MVP_D_FACE_DOUBLE_QUALITY": "needs_retake"}, timeout=180)
        if CC.scalar(f"SELECT (status='needs_retake')::int FROM skin_assessments "
                     f"WHERE id='{tid}'") == "1":
            break
    assert CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'") == "needs_retake"
    pv1 = live.sql_json(f"SELECT photo_versions::text FROM skin_assessments WHERE id='{tid}'")
    v1 = {v["version"]: v["images"] for v in pv1["versions"]}[1]
    old_front = v1["front"]
    assert CC.scalar(f"SELECT state FROM media_objects WHERE id='{old_front}'") == "available"
    new_front = live._png() + b"V2-FRONT-RETAKE"
    md = {"expectedPhotoVersion": "1", "replacedViews": ["front"]}
    c2, b2 = live.multipart_a02(tok, str(uuid.uuid4()), tid, "2", md, {"front": new_front})
    _rec(se, "PUT", f"/api/v1/skin-assessment-tasks/{tid}/photo-versions/2", c2, b2)
    cur = CC.scalar(f"SELECT current_photo_version FROM skin_assessments WHERE id='{tid}'")
    rev = CC.scalar(f"SELECT processing_revision FROM skin_assessments WHERE id='{tid}'")
    pv2 = live.sql_json(f"SELECT photo_versions::text FROM skin_assessments WHERE id='{tid}'")
    v2 = {v["version"]: v["images"] for v in pv2["versions"]}[2]
    jobs2 = CC.scalar("SELECT count(*) FROM async_jobs WHERE owner_id="
                      f"'{tid}' AND job_type='assessment.analyze' AND input_revision=2")
    assert c2 == 202 and (b2.get("data") or {}).get("photoVersion") == "2", (c2, b2)
    assert cur == "2" and rev == "2", (cur, rev)
    assert v2["front"] != old_front, (v2, old_front)
    assert v2["left"] == v1["left"] and v2["right"] == v1["right"]  # 未替换视角继承受控
    assert jobs2 == "1", jobs2
    assert CC.scalar(f"SELECT state FROM media_objects WHERE id='{old_front}'") == "available"
    # 跨云台：他云台补拍同一 taskId → 404 RESOURCE_NOT_VISIBLE 且零业务写入
    _g2, tok2 = live.gimbal_with_token()
    pv_before = CC.scalar(f"SELECT photo_versions::text FROM skin_assessments WHERE id='{tid}'")
    task_jobs_before = CC.scalar(f"SELECT count(*) FROM async_jobs WHERE owner_id='{tid}'")
    c3, b3 = live.multipart_a02(tok2, str(uuid.uuid4()), tid, "3",
                                {"expectedPhotoVersion": "2", "replacedViews": ["front"]},
                                {"front": live._png()})
    _rec(se, "PUT", f"/api/v1/skin-assessment-tasks/{tid}/photo-versions/3", c3, b3,
         req={"gimbal": "cross"})
    assert c3 == 404 and b3["error"]["code"] == "RESOURCE_NOT_VISIBLE", (c3, b3)
    assert CC.scalar(f"SELECT current_photo_version FROM skin_assessments WHERE id='{tid}'") == "2"
    assert CC.scalar(f"SELECT photo_versions::text FROM skin_assessments WHERE id='{tid}'") == pv_before
    # 零业务写入：本任务 job 数不变，且不产生 v3 的 analyze 任务
    assert CC.scalar(f"SELECT count(*) FROM async_jobs WHERE owner_id='{tid}'") == task_jobs_before
    assert CC.scalar("SELECT count(*) FROM async_jobs WHERE owner_id="
                     f"'{tid}' AND job_type='assessment.analyze' AND input_revision=3") == "0"
    # 正常 worker 推进 v2 至 report_ready（报告反映 v2，未被旧结果覆盖）
    ok = _worker_until(se, f"SELECT (status='report_ready')::int FROM skin_assessments "
                           f"WHERE id='{tid}'", cycles=60)
    repv = CC.scalar(f"SELECT report_photo_version FROM skin_assessments WHERE id='{tid}'")
    assert ok and repv == "2", (ok, repv)
    se.seal()


@_mark("SC-02-09", "P0", "集成", ["D"], ["D04", "D06"])
def test_SC_02_09(scenario_evidence):
    """SC-02-09 迟到返回 barrier（b40 十步）：真实租约自然过期 → 接管 → 补拍 v2 →
    A 的旧结果迟到返回被既有围栏拒绝，已发布 v2 快照逐值不变、无 sentinel 残留。"""
    se = scenario_evidence
    _decl(se)
    # 0) 排空 queued（仅真实消费，不改 job 业务列）
    for _ in range(60):
        if CC.scalar("SELECT count(*) FROM async_jobs WHERE status='queued' "
                     "AND available_at<=CURRENT_TIMESTAMP") == "0":
            break
        I.worker_once(timeout=180)
    g, tok = live.gimbal_with_token()
    front = live.marker_image("b40")
    marker = live.sha256_hex(front)
    images = {"front": front, "left": live._png() + b"L", "right": live._png() + b"R"}
    c, b = live.multipart_a01(tok, str(uuid.uuid4()), images=images)
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b, req={"marker_sha256": marker[:12]})
    tid = (b.get("data") or {}).get("taskId")
    assert c == 202 and tid, (c, b)
    d = live.barrier_dir("sc0209")
    released = d / "released"
    consumed = d / "consumed"
    if released.exists():
        released.unlink()
    base_env = {**live.barrier_env(d, marker, 180),
                "MVP_WORKER_CLAIM_BATCH": "1",
                "MVP_WORKER_LEASE_SECONDS": "2",
                "MVP_WORKER_RENEW_INTERVAL_SECONDS": "600"}
    proc_a, log_a = live.start_bg_worker(base_env, "sc0209-workerA.log")
    try:
        # 1) A 进入 barrier：consumed 出现；T05 analyzing；J1 owner/rev/attempt
        assert live.wait_path(consumed, 60), "worker A 未进入 barrier（consumed 未出现）"
        st = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
        o1 = CC.scalar("SELECT coalesce(lease_owner,'') FROM async_jobs WHERE owner_id="
                       f"'{tid}' AND job_type='assessment.analyze' AND input_revision=1")
        r1 = CC.scalar("SELECT lease_revision FROM async_jobs WHERE owner_id="
                       f"'{tid}' AND job_type='assessment.analyze' AND input_revision=1")
        a1 = CC.scalar("SELECT attempt_count FROM async_jobs WHERE owner_id="
                       f"'{tid}' AND job_type='assessment.analyze' AND input_revision=1")
        _audit(se, "SC-02-09 A in barrier", 0,
               {"assessment": st, "owner": o1, "lease_revision": r1, "attempt": a1})
        assert st == "analyzing" and o1 != "" and r1 == "1" and a1 == "1", (st, o1, r1, a1)
        # 2) 自然租约过期 + --recover（既有回收路径，不关续租）
        time.sleep(2.5)
        I.worker_cli("--recover", timeout=120)
        st2 = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
        o2 = CC.scalar("SELECT coalesce(lease_owner,'') FROM async_jobs WHERE owner_id="
                       f"'{tid}' AND job_type='assessment.analyze' AND input_revision=1")
        r2 = CC.scalar("SELECT lease_revision FROM async_jobs WHERE owner_id="
                       f"'{tid}' AND job_type='assessment.analyze' AND input_revision=1")
        jst2 = CC.scalar("SELECT status FROM async_jobs WHERE owner_id="
                         f"'{tid}' AND job_type='assessment.analyze' AND input_revision=1")
        assert jst2 == "queued" and o2 == "" and int(r2) >= 2, (jst2, o2, r2, st2)
        # 3) 接管者 B（同一组 barrier env；一次性语义使其立即返回）
        env_b = {**live.barrier_env(d, marker, 180),
                 "MVP_WORKER_CLAIM_BATCH": "1",
                 "MVP_D_FACE_DOUBLE_QUALITY": "needs_retake",
                 "MVP_D_FACE_DOUBLE_REQUIRED_VIEWS": "front"}
        I.worker_once(env_extra=env_b, timeout=180)
        j1 = CC.scalar("SELECT status FROM async_jobs WHERE owner_id="
                       f"'{tid}' AND job_type='assessment.analyze' AND input_revision=1")
        a2 = CC.scalar("SELECT attempt_count FROM async_jobs WHERE owner_id="
                       f"'{tid}' AND job_type='assessment.analyze' AND input_revision=1")
        st3 = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
        assert j1 == "succeeded" and a2 == "2", (j1, a2)
        assert st3 == "needs_retake", st3
        # 4) 真实 M3-A02 补拍 v2
        md = {"expectedPhotoVersion": "1", "replacedViews": ["front"]}
        c2, b2 = live.multipart_a02(tok, str(uuid.uuid4()), tid, "2", md,
                                    {"front": live._png() + b"V2-RETAKE"})
        _rec(se, "PUT", f"/api/v1/skin-assessment-tasks/{tid}/photo-versions/2", c2, b2)
        assert c2 == 202 and (b2.get("data") or {}).get("photoVersion") == "2", (c2, b2)
        cur = CC.scalar(f"SELECT current_photo_version FROM skin_assessments WHERE id='{tid}'")
        prev = CC.scalar(f"SELECT processing_revision FROM skin_assessments WHERE id='{tid}'")
        j2 = CC.scalar("SELECT count(*) FROM async_jobs WHERE owner_id="
                       f"'{tid}' AND job_type='assessment.analyze' AND input_revision=2")
        assert cur == "2" and prev == "2" and j2 == "1", (cur, prev, j2)
        # 5) Worker C：正常 env 循环至 report_ready，拍快照
        ok = _worker_until(se, f"SELECT (status='report_ready')::int FROM skin_assessments "
                               f"WHERE id='{tid}'", cycles=80,
                           env_extra={"MVP_WORKER_BACKOFF_BASE_SECONDS": "0",
                                      "MVP_WORKER_CLAIM_BATCH": "5"})
        assert ok, "worker C 未达 report_ready"
        snap_cols = ("report_id", "report_payload", "report_summary", "member_id",
                     "report_photo_version")
        snap = {col: CC.scalar(f"SELECT coalesce(({col})::text,'') FROM skin_assessments "
                               f"WHERE id='{tid}'") for col in snap_cols}
        members_after_c = CC.scalar("SELECT count(*) FROM members")
        assert snap["report_photo_version"] == "2", snap
        # 6) 释放 A；等其退出；既有围栏告警
        released.write_text("release", encoding="utf-8")
        proc_a.wait(timeout=90)
        stale_warn = live.log_has(log_a, "job.complete_stale_generation")
        _audit(se, "SC-02-09 A released old result fenced", 0,
               {"stale_warning": stale_warn, "a_rc": proc_a.returncode})
        assert stale_warn, live.log_text(log_a)[-800:]
        # 7) 最终：v2 快照逐值未变、唯一报告、无 sentinel 残留
        snap2 = {col: CC.scalar(f"SELECT coalesce(({col})::text,'') FROM skin_assessments "
                                f"WHERE id='{tid}'") for col in snap_cols}
        assert snap2 == snap, (snap, snap2)
        assert CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE id='{tid}' "
                         "AND status='report_ready'") == "1"
        assert CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE gimbal_id='{g}'") == "1"
        assert CC.scalar("SELECT count(*) FROM members") == members_after_c
        assert not consumed.exists() and not released.exists()
    finally:
        live.stop_bg_worker(proc_a)
    se.seal()


@_mark("SC-02-10", "P1", "集成", ["D"], ["D06", "D07"])
def test_SC_02_10(scenario_evidence):
    """算法违约注入 → 1 轮确定性终态 PROVIDER_CONTRACT_VIOLATION；无后继 job、
    查询不触发新分析、不泄漏内部诊断；复位对照达 report_ready。"""
    se = scenario_evidence
    se.doubles.add("face_algo", "double", "D FaceDouble")
    se.doubles.add("skin_algo", "double", "D SkinDouble")
    se.doubles.add("oss", "double", "A FilesystemStorageDouble")
    se.doubles.add("gimbal_device", "double", "云台会话 dev 凭据")

    def _terminal(shape: str):
        g, tok = live.gimbal_with_token()
        c, b = live.multipart_a01(tok, str(uuid.uuid4()))
        _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b, req={"inject": shape})
        tid = (b.get("data") or {}).get("taskId")
        assert c == 202 and tid, (c, b)
        I.worker_once(env_extra={"MVP_D_SKIN_DOUBLE_INVALID": shape}, timeout=180)
        st = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
        fc = CC.scalar(f"SELECT coalesce(failure_code,'') FROM skin_assessments WHERE id='{tid}'")
        rep = CC.scalar(f"SELECT coalesce(report_id::text,'')||coalesce(report_payload::text,'') "
                        f"FROM skin_assessments WHERE id='{tid}'")
        jst = CC.scalar("SELECT status FROM async_jobs WHERE owner_id="
                        f"'{tid}' AND job_type='assessment.analyze'")
        jatt = CC.scalar("SELECT attempt_count FROM async_jobs WHERE owner_id="
                         f"'{tid}' AND job_type='assessment.analyze'")
        jerr = live.sql_json("SELECT last_error::text FROM async_jobs WHERE owner_id="
                             f"'{tid}' AND job_type='assessment.analyze'")
        jrows = CC.scalar(f"SELECT count(*) FROM async_jobs WHERE owner_id='{tid}'")
        return g, tok, tid, st, fc, rep, jst, jatt, jerr, jrows

    # 主形态 out_of_range：全量断言
    g, tok, tid, st, fc, rep, jst, jatt, jerr, jrows = _terminal("out_of_range")
    _audit(se, "SC-02-10 out_of_range terminal", 0,
           {"status": st, "failure_code": fc, "job_status": jst, "attempt": jatt})
    assert st == "failed", st
    assert fc == "PROVIDER_CONTRACT_VIOLATION", fc
    assert rep == "", rep
    assert jst == "failed" and jatt == "1", (jst, jatt)
    assert jerr and jerr.get("retryable") is False, jerr
    assert jrows == "1", jrows  # 无 identity.enroll / plan.generate 后继
    # M3-A03 GET：同值 failureCode、无 failure_detail/reason/stack 泄漏、查询不产生新 job
    jobs_before = CC.scalar("SELECT count(*) FROM async_jobs")
    cq, bq, _ = I.http("GET", f"/api/v1/skin-assessment-tasks/{tid}", token=tok)
    _rec(se, "GET", f"/api/v1/skin-assessment-tasks/{tid}", cq, bq)
    jobs_after = CC.scalar("SELECT count(*) FROM async_jobs")
    raw = json.dumps(bq, ensure_ascii=False)
    data = bq.get("data") or {}
    _audit(se, "SC-02-10 A03 projection", cq, {"failureCode": data.get("failureCode"),
                                               "retryable": data.get("retryable")})
    assert cq == 200 and data.get("status") == "failed", (cq, bq)
    assert data.get("failureCode") == "PROVIDER_CONTRACT_VIOLATION"
    assert data.get("retryable") is False and data.get("reportId") is None
    assert "failure_detail" not in raw and '"reason"' not in raw and "stack" not in raw
    assert jobs_before == jobs_after
    # 再跑同 env 不增 attempt
    I.worker_once(env_extra={"MVP_D_SKIN_DOUBLE_INVALID": "out_of_range"}, timeout=180)
    jatt2 = CC.scalar("SELECT attempt_count FROM async_jobs WHERE owner_id="
                      f"'{tid}' AND job_type='assessment.analyze'")
    assert jatt2 == "1", jatt2
    # 抽验另两形态：确定性终态一致
    for shape in ("unknown_metric", "bad_unit"):
        _g2, _t2, tid2, st2, fc2, rep2, jst2, jatt2, _e2, jr2 = _terminal(shape)
        _audit(se, f"SC-02-10 spot {shape}", 0,
               {"status": st2, "failure_code": fc2, "attempt": jatt2, "jobs": jr2})
        assert (st2, fc2, rep2, jst2, jatt2, jr2) == \
            ("failed", "PROVIDER_CONTRACT_VIOLATION", "", "failed", "1", "1"), \
            (shape, st2, fc2, rep2, jst2, jatt2, jr2)
    # 复位对照（不设旋钮）→ report_ready
    _g3, tok3 = live.gimbal_with_token()
    c3, b3 = live.multipart_a01(tok3, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c3, b3, req={"inject": "off"})
    tid3 = (b3.get("data") or {}).get("taskId")
    ok3 = _worker_until(se, f"SELECT (status='report_ready')::int FROM skin_assessments "
                            f"WHERE id='{tid3}'")
    _audit(se, "SC-02-10 injection-off control reaches report_ready", 0, {"ready": ok3})
    assert c3 == 202 and ok3, (c3, ok3)
    se.seal()


@_mark("SC-02-05", "P1", "集成", ["D"], ["D06"])
def test_SC_02_05(scenario_evidence):
    """质量不合格注入 → 真实 M3-A01 受理 → worker needs_retake 补拍态；关闭注入恢复正常。"""
    se = scenario_evidence
    _decl(se)
    _g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b, req={"inject": "needs_retake"})
    tid = (b.get("data") or {}).get("taskId")
    assert c == 202 and tid, (c, b)
    inj = {"MVP_D_FACE_DOUBLE_QUALITY": "needs_retake",
           "MVP_D_FACE_DOUBLE_REQUIRED_VIEWS": "front,left"}
    reached = False
    for _ in range(6):
        I.worker_once(env_extra=inj, timeout=180)
        if CC.scalar(f"SELECT (status='needs_retake')::int FROM skin_assessments "
                     f"WHERE id='{tid}'") == "1":
            reached = True
            break
    st = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
    fc = CC.scalar(f"SELECT coalesce(failure_code,'') FROM skin_assessments WHERE id='{tid}'")
    ir = live.sql_json(f"SELECT identity_result::text FROM skin_assessments WHERE id='{tid}'")
    ready_rows = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE id='{tid}' "
                           "AND status='report_ready'")
    reports = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE id='{tid}' "
                        "AND report_payload IS NOT NULL")
    _audit(se, "SC-02-05 injected needs_retake terminal", 0,
           {"status": st, "failure_code": fc,
            "required_views": (ir or {}).get("quality", {}).get("required_views")})
    assert reached and st == "needs_retake", (reached, st)
    assert fc == "QUALITY_REJECTED", fc
    assert ir and ir.get("quality", {}).get("status") == "needs_retake", ir
    assert ir.get("quality", {}).get("required_views") == ["front", "left"], ir
    assert ready_rows == "0" and reports == "0"
    # 关闭注入对照（无 env）：全新任务恢复正常达 report_ready
    _g2, tok2 = live.gimbal_with_token()
    c2, b2 = live.multipart_a01(tok2, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"inject": "off"})
    tid2 = (b2.get("data") or {}).get("taskId")
    ok2 = _worker_until(se, f"SELECT (status='report_ready')::int FROM skin_assessments "
                            f"WHERE id='{tid2}'")
    _audit(se, "SC-02-05 injection-off control reaches report_ready", 0, {"ready": ok2})
    assert c2 == 202 and ok2, (c2, ok2)
    se.seal()


@_mark("SC-02-06", "P0", "集成", ["D"], ["D06"])
def test_SC_02_06(scenario_evidence):
    """三视角非同人 / 身份不确定注入 → 不误归成员、不自动建档、不出报告。"""
    se = scenario_evidence
    _decl(se)
    members_before = CC.scalar("SELECT count(*) FROM members")

    def _run(env, label):
        g, tok = live.gimbal_with_token()
        c, b = live.multipart_a01(tok, str(uuid.uuid4()))
        _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b, req={"inject": label})
        tid = (b.get("data") or {}).get("taskId")
        assert c == 202 and tid, (c, b)
        for _ in range(6):
            I.worker_once(env_extra=env, timeout=180)
            if CC.scalar(f"SELECT (status='needs_retake')::int FROM skin_assessments "
                         f"WHERE id='{tid}'") == "1":
                break
        st = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid}'")
        fc = CC.scalar(f"SELECT coalesce(failure_code,'') FROM skin_assessments WHERE id='{tid}'")
        mid = CC.scalar(f"SELECT coalesce(member_id::text,'') FROM skin_assessments WHERE id='{tid}'")
        reports = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE id='{tid}' "
                            "AND report_payload IS NOT NULL")
        ir = live.sql_json(f"SELECT identity_result::text FROM skin_assessments WHERE id='{tid}'")
        _audit(se, f"SC-02-06 injected {label}", 0,
               {"status": st, "failure_code": fc, "member_id": mid,
                "classification": (ir or {}).get("classification")})
        assert st == "needs_retake", (label, st)
        assert mid == "", (label, mid)
        assert reports == "0", (label, reports)
        return fc, ir

    # 分支①：非同人 → NOT_SAME_PERSON（members 不增 / member_id 未误置 / 无报告）
    fc1, ir1 = _run({"MVP_D_FACE_DOUBLE_SAME_PERSON": "false"}, "same_person=false")
    assert fc1 == "NOT_SAME_PERSON", fc1
    assert ir1.get("classification") == "not_same_person", ir1
    # 分支②：1:N 不确定 → IDENTITY_UNCERTAIN（不建档、不出报告）
    fc2, ir2 = _run({"MVP_D_FACE_DOUBLE_SEARCH": "uncertain"}, "search=uncertain")
    assert fc2 == "IDENTITY_UNCERTAIN", fc2
    assert ir2.get("classification") == "uncertain", ir2

    members_after = CC.scalar("SELECT count(*) FROM members")
    assert members_before == members_after, (members_before, members_after)
    se.seal()


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
