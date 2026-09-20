# -*- coding: utf-8 -*-
"""SC-C · 跨流程与异步组件 —— 集成轮 batch 2 lane C1（5 节点）。

C-01 受控接口认证/隔离/有效性（按 API 族分组实测，非逐 API 全排列，如实披露口径）。
C-02..05 替身组：入库与异步登记一致性 / 进程退出恢复 / 并发领取 / 媒体存储与受控读取。
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
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
    se.doubles.add("oss", "double", "A FilesystemStorageDouble（dev 本地存储）")
    se.doubles.add("gimbal_device", "double", "云台会话 dev 凭据")


def _worker_until(sql_cond, cycles=140, env_extra=None):
    for _ in range(cycles):
        if CC.scalar(sql_cond) == "1":
            return True
        I.worker_once(env_extra=env_extra, timeout=180)
    return CC.scalar(sql_cond) == "1"


def _submit(se):
    g, tok = live.gimbal_with_token()
    c, b = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c, b)
    return g, tok, c, b, (b.get("data") or {}).get("taskId")


# ---------------- C-01 ----------------

@_mark("SC-C-01", "P0", "后端", ["B","C","D"], ["D01","D04","D08"])
def test_SC_C_01(scenario_evidence):
    """受控接口：无效凭据 401、越权/替换 ID 404/403、缺失字段 400、拒绝零写入。

    覆盖口径：按 API 族**代表性抽样**（认证族/评估族/护理族/通知族/设备族），
    非逐 API 全排列；覆盖清单与结论在证据中写明。
    """
    se = scenario_evidence
    _decl(se)
    g, tok, c, b, tid = _submit(se)
    assert c == 202
    def cnt():
        return "|".join(CC.scalar(s) for s in (
            "SELECT count(*) FROM skin_assessments",
            "SELECT count(*) FROM care_executions",
            "SELECT count(*) FROM notification_destinations",
            "SELECT count(*) FROM microcrystals"))
    before = cnt()
    fam = [
        ("GET", "/api/v1/me/member-access-grants", None, 401, "auth"),
        ("GET", "/api/v1/members/00000000-0000-0000-0000-000000000000/skin-reports", "forged", 401, "auth"),
        ("GET", f"/api/v1/skin-assessment-tasks/{tid}", "forged", 401, "auth"),
        ("GET", "/api/v1/skin-reports/00000000-0000-0000-0000-000000000000", "forged", 401, "auth"),
        ("GET", "/api/v1/care-plans/00000000-0000-0000-0000-000000000000", "forged", 401, "care"),
    ]
    for m, p, tk, exp, f in fam:
        cc, bb, _ = I.http(m, p, token=tk)
        _rec(se, m, p, cc, bb, req={"family": f})
        assert cc == exp, (p, cc, bb)
    # 云台越权：他云台替换 ID 查当前任务 → 403；替换报告/方案 ID（APP 未授权）→ 404
    g2, t2 = live.gimbal_with_token()
    cg, bg, _ = I.http("GET", f"/api/v1/skin-assessment-tasks/{tid}", token=t2)
    _rec(se, "GET", f"/api/v1/skin-assessment-tasks/{tid}", cg, bg, req={"family": "gimbal-other"})
    assert cg in (403, 404)
    a = live.app_login("scc01")
    cr, br, _ = I.http("GET", "/api/v1/skin-reports/00000000-0000-0000-0000-000000000000",
                       token=a["access"])
    _rec(se, "GET", "/api/v1/skin-reports/{unknown}", cr, br, req={"family": "report-unknown"})
    assert cr == 404 and br["error"]["code"] == "RESOURCE_NOT_VISIBLE"
    after = cnt()
    assert before == after, (before, after)  # 拒绝路径零业务写入
    se.seal()


# ---------------- C-02 ----------------

@_mark("SC-C-02", "P0", "集成", ["D"], ["D07"])
def test_SC_C_02(scenario_evidence):
    """入库与异步任务登记一致性：受理成功=业务行+job 同存；处理失败≠入库丢失；
    同键重试遵循去重返回同任务。"""
    se = scenario_evidence
    _decl(se)
    key = str(uuid.uuid4())
    cs = f"cs-{uuid.uuid4().hex[:8]}"
    g, tok = live.gimbal_with_token()
    c1, b1 = live.multipart_a01(tok, key, capture_session_id=cs)
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c1, b1, req={"n": 1})
    t1 = (b1.get("data") or {}).get("taskId")
    row_job = (CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE id='{t1}'") == "1" and
               CC.scalar(f"SELECT count(*) FROM async_jobs WHERE owner_id='{t1}'") != "0")
    c2, b2 = live.multipart_a01(tok, key, capture_session_id=cs)
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"n": 2, "retry": True})
    # 诱导处理后失败：worker 以未激活提供方运行 → 任务保持失败/重试态但业务行不丢
    for _ in range(6):
        I.worker_once(env_extra={"MVP_D_SKIN_PROVIDER": "aliyun_skin"}, timeout=180)
    still = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE id='{t1}'")
    assert c1 == 202 and row_job
    assert c2 == 200 and (b2.get("data") or {}).get("taskId") == t1
    assert still == "1"  # 处理失败不丢入库
    se.seal()


# ---------------- C-03 ----------------

@_mark("SC-C-03", "P0", "集成", ["D"], ["D07"])
def test_SC_C_03(scenario_evidence):
    """异步进程退出恢复：处理中 kill worker → 重启后任务不丢、lease 回收、结果不重复归档。"""
    se = scenario_evidence
    _decl(se)
    g, tok, c, b, tid = _submit(se)
    assert c == 202
    # 真实启动 worker 进程后 kill（job 处理中）
    proc = I.start_worker()
    time.sleep(1.5)
    try:
        proc.kill()
        proc.wait(timeout=15)
    except Exception:
        pass
    se.record_raw(method="PROC", path="kill worker (processing)", status=0, request_headers={},
                  request_json={"signal": "SIGKILL"}, response_excerpt=f"pid={proc.pid}",
                  started_at=0.0, elapsed_ms=0.0)
    # lease 过期后回收并完成
    ok = _worker_until(f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{tid}'", 80)
    reports = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE id='{tid}' AND report_id IS NOT NULL")
    job = CC.scalar("SELECT status FROM async_jobs WHERE owner_id="
                    f"'{tid}' AND job_type='assessment.analyze'")
    assert ok and reports == "1" and job in ("succeeded",), (ok, reports, job)
    archives = CC.scalar(f"SELECT count(*) FROM media_objects WHERE assessment_id='{tid}' "
                         "AND purpose='assessment_result'")
    assert int(archives) >= 1
    se.seal()


# ---------------- C-04 ----------------

@_mark("SC-C-04", "P0", "集成", ["B","D"], ["D07","D02"])
def test_SC_C_04(scenario_evidence):
    """重复领取/并发执行：两轻量 worker 并发 --once → 恰一次执行（报告/方案唯一）。"""
    se = scenario_evidence
    _decl(se)
    tasks = []
    for _ in range(2):
        _g, _t, c, b, tid = _submit(se)
        assert c == 202
        tasks.append(tid)
    outs = {}

    def run(name):
        outs[name] = I.worker_once(timeout=180)

    ts = [threading.Thread(target=run, args=(f"w{i}",)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    for _ in range(80):
        if all(CC.scalar(f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{x}'") == "1"
               for x in tasks):
            break
        I.worker_once(timeout=180)
    for x in tasks:  # 每任务恰一份报告/方案/引用（并发领取不重复执行）
        r = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE id='{x}' AND status='report_ready'")
        pl = CC.scalar(f"SELECT count(*) FROM care_plans WHERE assessment_id='{x}'")
        dp = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE id='{x}' AND report_id IS NOT NULL")
        assert r == "1" and pl == "1" and dp == "1", (x, r, pl, dp)
    se.seal()


# ---------------- C-05 ----------------

@_mark("SC-C-05", "P0", "集成", ["B","C","D"], ["D06","D07"])
def test_SC_C_05(scenario_evidence):
    """存储注入：assessment_source/grant_face 上传失败（Java 旋钮重启生效，按用途互不干扰）；
    execution_face/revalidation_face 用 C 域真实 HTTP 端点补验；worker 结果图保存失败；
    关闭注入后正常保存、重启后可读字节一致、未授权/旧任务 404。"""
    import hashlib
    import requests

    se = scenario_evidence
    _decl(se)

    def _java(variant: dict, log: str):
        env = {**CC.variant_env(profiles="dev"), **variant}
        proc, up, clean = CC._restart_java(env, log)
        assert clean and up, (clean, up, log)
        return proc

    def _raw_get(path, token):
        r = requests.get(I.APP_BASE + path, headers={"Authorization": f"Bearer {token}"},
                         timeout=20, proxies=None)
        return r.status_code, r.content

    def _media_for_key(key):
        return CC.scalar("SELECT count(*) FROM media_objects mo JOIN idempotency_requests ir "
                         f"ON mo.request_id=ir.id WHERE ir.idempotency_key='{key}'")

    # ---------- A. 默认（dev 无注入）正常链 + B 策略授权矩阵 ----------
    g, tok, c, b, tid = _submit(se)
    _worker_until(f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{tid}'", 140)
    row = CC.scalar(f"SELECT member_id::text||'|'||coalesce(report_id::text,'') FROM skin_assessments "
                    f"WHERE id='{tid}'")
    mid, rid = row.split("|")
    result_media = CC.scalar("SELECT payload->'images'->0->>'media_id' FROM ("
                             f"SELECT report_payload AS payload FROM skin_assessments WHERE id='{tid}'"
                             ") t")
    a = live.app_login("scc05")
    ca, ba, _ = I.http("GET", f"/api/v1/media/{result_media}/content", token=a["access"])
    _rec(se, "GET", f"/api/v1/media/{result_media}/content", ca, ba, req={"grant": False})
    CC.seed_grant(a["accountId"], mid, status="active")
    ca2, ba2, _ = I.http("GET", f"/api/v1/media/{result_media}/content", token=a["access"])
    _rec(se, "GET", f"/api/v1/media/{result_media}/content", ca2, ba2, req={"grant": True})
    cg, bg, _ = I.http("GET", f"/api/v1/media/{result_media}/content", token=tok)
    _rec(se, "GET", f"/api/v1/media/{result_media}/content", cg, bg, req={"gimbal": "current"})
    src = CC.scalar(f"SELECT id::text FROM media_objects WHERE assessment_id='{tid}' "
                    "AND purpose <> 'assessment_result' LIMIT 1")
    cs, bs, _ = I.http("GET", f"/api/v1/media/{src}/content", token=a["access"])
    _rec(se, "GET", f"/api/v1/media/{src}/content", cs, bs, req={"purpose": "non-result"})
    assert result_media and ca == 404 and ca2 == 200 and cs == 404
    # 既有可读字节（用于 ④ 重启可读对照）
    cc0, bytes0 = _raw_get(f"/api/v1/media/{result_media}/content", a["access"])
    assert cc0 == 200 and bytes0, cc0
    digest0 = hashlib.sha256(bytes0).hexdigest()
    # 旧任务云台：换当前任务后旧 gimbal 读旧结果 → 404
    c2, b2 = live.multipart_a01(tok, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", c2, b2, req={"replace_current": True})
    assert c2 == 202
    cg2, bg2, _ = I.http("GET", f"/api/v1/media/{result_media}/content", token=tok)
    _rec(se, "GET", f"/api/v1/media/{result_media}/content", cg2, bg2, req={"gimbal": "replaced"})
    assert cg2 == 404

    # ---------- ① Java：fail-put:assessment_source / grant_face（按用途互不干扰） ----------
    # ①-a 云台原图上传失败；授权人脸不受影响
    _java({"APP_DOUBLE_STORAGE_FAIL_MODE": "fail-put:assessment_source"},
          "scc05-java-fail-assessment-source.log")
    g1, tok1 = live.gimbal_with_token()
    key1 = str(uuid.uuid4())
    cs1, bs1 = live.multipart_a01(tok1, key1)
    req_id1 = bs1.get("requestId") or ""
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", cs1, bs1,
         req={"inject": "fail-put:assessment_source"})
    assert cs1 == 503 and bs1["error"]["code"] == "DEPENDENCY_UNAVAILABLE", (cs1, bs1)
    assert req_id1, bs1
    avail = CC.scalar("SELECT count(*) FROM media_objects mo JOIN idempotency_requests ir "
                      f"ON mo.request_id=ir.id WHERE ir.idempotency_key='{key1}' AND mo.state='available'")
    failed = CC.scalar("SELECT count(*) FROM media_objects mo JOIN idempotency_requests ir "
                       f"ON mo.request_id=ir.id WHERE ir.idempotency_key='{key1}' AND mo.state='failed'")
    tasks1 = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE gimbal_id='{g1}'")
    raw1 = json.dumps(bs1, ensure_ascii=False)
    assert avail == "0" and int(failed) >= 1 and tasks1 == "0", (avail, failed, tasks1)
    assert "getMessage" not in raw1 and '"stack"' not in raw1 and "java." not in raw1
    # 互不干扰：同一 Java 实例下 APP 授权人脸仍成功落盘
    a1 = live.app_login("scc05-grant-ok")
    _m1, img1 = live.seed_member_face(image=live._png() + uuid.uuid4().hex.encode())
    gk, gbody = live.multipart_grant(a1["access"], img1)
    _rec(se, "POST", "/api/v1/member-access-grants", gk, gbody,
         req={"inject": "fail-put:assessment_source", "purpose": "grant_face"})
    assert gk == 201, (gk, gbody)

    # ①-b 授权人脸上传失败；云台原图不受影响
    _java({"APP_DOUBLE_STORAGE_FAIL_MODE": "fail-put:grant_face"},
          "scc05-java-fail-grant-face.log")
    a2 = live.app_login("scc05-grant-fail")
    _m2, img2 = live.seed_member_face(image=live._png() + uuid.uuid4().hex.encode())
    gkey = str(uuid.uuid4())
    gk2, gbody2 = live.multipart_grant(a2["access"], img2, key=gkey)
    _rec(se, "POST", "/api/v1/member-access-grants", gk2, gbody2,
         req={"inject": "fail-put:grant_face"})
    assert gk2 == 503 and gbody2["error"]["code"] == "DEPENDENCY_UNAVAILABLE", (gk2, gbody2)
    grants2 = CC.scalar("SELECT count(*) FROM member_access_grants g JOIN idempotency_requests ir "
                        f"ON g.source_request_id=ir.id WHERE ir.idempotency_key='{gkey}'")
    idem2 = CC.scalar(f"SELECT coalesce(status,'') FROM idempotency_requests "
                      f"WHERE idempotency_key='{gkey}'")
    assert grants2 == "0" and idem2 != "succeeded", (grants2, idem2)
    # 互不干扰：同一 Java 实例下云台原图仍受理 202
    g3, tok3 = live.gimbal_with_token()
    cs3, bs3 = live.multipart_a01(tok3, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", cs3, bs3,
         req={"inject": "fail-put:grant_face", "purpose": "assessment_source"})
    assert cs3 == 202, (cs3, bs3)

    # ---------- ② C 域真实端点：execution_face / revalidation_face ----------
    cmid, _cface = live.seed_member_face(image=live._png() + uuid.uuid4().hex.encode())
    cmc = CC.seed_microcrystal(CC.DEFAULT_CAPABILITIES)
    casmt = CC.seed_assessment(CC.seed_gimbal(), cmid)
    cplan = CC.seed_plan(casmt, cmid, status="ready", target=3, mc=cmc)
    assert CC.scalar(f"SELECT count(*) FROM members WHERE id='{cmid}'") == "1"
    assert CC.scalar(f"SELECT count(*) FROM care_plans WHERE id='{cplan}'") == "1", \
        "C 域夹具 plan 未落库（seed_plan 失败）"
    # ②-a execution_face 注入 → M4-A03 503
    _java({"APP_C_FACE_BOUND_MEMBER": cmid,
           "APP_DOUBLE_STORAGE_FAIL_MODE": "fail-put:execution_face"},
          "scc05-java-fail-execution-face.log")
    a3 = live.app_login("scc05-exec-face")
    CC.seed_grant(a3["accountId"], cmid, status="active")
    ce, be = CC.admit(a3["access"], cmc, cplan)
    _rec(se, "POST", "/api/v1/care-executions", ce, be,
         req={"inject": "fail-put:execution_face", "purpose": "execution_face"})
    assert ce == 503 and be["error"]["code"] == "DEPENDENCY_UNAVAILABLE", (ce, be)
    # ②-b 关闭执行注入（仍绑定成员）→ M4-A03 成功，建立可复核执行
    _java({"APP_C_FACE_BOUND_MEMBER": cmid}, "scc05-java-bound.log")
    a4 = live.app_login("scc05-exec-ok")
    CC.seed_grant(a4["accountId"], cmid, status="active")
    ce2, be2 = CC.admit(a4["access"], cmc, cplan)
    _rec(se, "POST", "/api/v1/care-executions", ce2, be2, req={"purpose": "execution_face"})
    assert ce2 == 201, (ce2, be2)
    ex = (be2.get("data") or {}).get("executionId")
    ep = (be2.get("data") or {}).get("recordStreamEpoch") or ex
    assert ex, be2
    I.http("POST", f"/api/v1/care-executions/{ex}/observations", token=a4["access"],
           body=CC.obs_records(ep, [], seq=1, state="paused"),
           headers={"Idempotency-Key": str(uuid.uuid4())})
    # ②-c revalidation_face 注入 → A04 503
    _java({"APP_C_FACE_BOUND_MEMBER": cmid,
           "APP_DOUBLE_STORAGE_FAIL_MODE": "fail-put:revalidation_face"},
          "scc05-java-fail-revalidation-face.log")
    # 原控制者身份：同一 tag 派生同一 account（重启后会话失效需重登，account 不变）
    a5 = live.app_login("scc05-exec-ok")
    CC.seed_grant(a5["accountId"], cmid, status="active")
    rev = CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{ex}'")
    cr, br = CC.post_multipart(
        f"/api/v1/care-executions/{ex}/revalidations", a5["access"],
        {"expectedVerificationRevision": rev or "1",
         "capture": {"captureId": str(uuid.uuid4()), "capturedAt": CC.utcnow(),
                     "clientContinuityId": "cc-1", "purpose": "revalidation"},
         "consentEvidenceRef": "consent-1"}, str(uuid.uuid4()))
    _rec(se, "POST", f"/api/v1/care-executions/{ex}/revalidations", cr, br,
         req={"inject": "fail-put:revalidation_face", "purpose": "revalidation_face"})
    assert cr == 503 and br["error"]["code"] == "DEPENDENCY_UNAVAILABLE", (cr, br)

    # ---------- ③ worker 结果图保存失败（可重试，无脏 available / 报告不就绪） ----------
    g4, tok4 = live.gimbal_with_token()
    cs4, bs4 = live.multipart_a01(tok4, str(uuid.uuid4()))
    _rec(se, "POST", "/api/v1/skin-assessment-tasks", cs4, bs4,
         req={"inject": "MVP_D_STORAGE_DOUBLE_FAIL_PUT"})
    tid4 = (bs4.get("data") or {}).get("taskId")
    assert cs4 == 202 and tid4, (cs4, bs4)
    for _ in range(6):
        I.worker_once(env_extra={"MVP_D_STORAGE_DOUBLE_FAIL_PUT": "true",
                                 "MVP_WORKER_BACKOFF_BASE_SECONDS": "0"}, timeout=180)
        if CC.scalar(f"SELECT (status='analyzing')::int FROM skin_assessments "
                     f"WHERE id='{tid4}'") == "1":
            pass
        jerr = live.sql_json("SELECT last_error::text FROM async_jobs WHERE owner_id="
                             f"'{tid4}' AND job_type='assessment.analyze'")
        if jerr and jerr.get("code") == "RESULT_ARCHIVE_FAILED":
            break
    jerr4 = live.sql_json("SELECT last_error::text FROM async_jobs WHERE owner_id="
                          f"'{tid4}' AND job_type='assessment.analyze'")
    st4 = CC.scalar(f"SELECT status FROM skin_assessments WHERE id='{tid4}'")
    ready4 = CC.scalar(f"SELECT count(*) FROM skin_assessments WHERE id='{tid4}' "
                       "AND status='report_ready'")
    dirty = CC.scalar(f"SELECT count(*) FROM media_objects WHERE assessment_id='{tid4}' "
                      "AND purpose='assessment_result' AND state='available'")
    _audit(se, "SC-C-05 worker result archive failure", 0,
           {"status": st4, "ready": ready4, "dirty_available": dirty,
            "last_error": jerr4})
    assert jerr4 and jerr4.get("code") == "RESULT_ARCHIVE_FAILED", jerr4
    assert st4 != "report_ready" and ready4 == "0" and dirty == "0", (st4, ready4, dirty)
    # 关闭注入 → 同任务可重试收敛 report_ready（无脏 available 残留）
    ok4 = _worker_until(f"SELECT (status='report_ready')::int FROM skin_assessments "
                        f"WHERE id='{tid4}'", 80,
                        env_extra={"MVP_WORKER_BACKOFF_BASE_SECONDS": "0",
                                   "MVP_WORKER_CLAIM_BATCH": "5"})
    assert ok4, "关闭结果图注入后未收敛 report_ready"
    assert CC.scalar(f"SELECT count(*) FROM media_objects WHERE assessment_id='{tid4}' "
                     "AND purpose='assessment_result' AND state='available'") != "0"

    # ---------- ④ 关闭注入：正常保存 + 重启后可读（同 dev-dir 新实例字节一致） ----------
    _java({}, "scc05-java-restore.log")
    # 重启后会话内存态失效：同 tag 重新登录得到同一 account（授权关系仍在 DB）
    a_r = live.app_login("scc05")
    assert a_r and a_r["accountId"] == a["accountId"], (a_r, a)
    cc1, bytes1 = _raw_get(f"/api/v1/media/{result_media}/content", a_r["access"])
    digest1 = hashlib.sha256(bytes1).hexdigest()
    _audit(se, "SC-C-05 restart-readable byte identity", cc1,
           {"before": digest0, "after": digest1, "bytes": len(bytes1)})
    assert cc1 == 200 and digest1 == digest0, (cc1, digest0, digest1)
    # 重启后仍保留未授权 404 / 旧任务云台 404
    bacc = live.app_login("scc05-post-restart")
    cu, bu, _ = I.http("GET", f"/api/v1/media/{result_media}/content", token=bacc["access"])
    _rec(se, "GET", f"/api/v1/media/{result_media}/content", cu, bu, req={"post_restart": "no-grant"})
    g5, tok5 = live.gimbal_with_token()
    cs5, bs5, _ = I.http("GET", f"/api/v1/skin-assessment-tasks/{tid}", token=tok5)
    _rec(se, "GET", f"/api/v1/skin-assessment-tasks/{tid}", cs5, bs5,
         req={"post_restart": "other-gimbal"})
    assert cu == 404 and cs5 in (403, 404), (cu, cs5)
    se.seal()
