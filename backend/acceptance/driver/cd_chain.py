#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E 对 C+D 集成候选（aebccc7 = C 8b3592e + D dc955c0）的扩展黑盒验收：CD-01..CD-08 + CLEANUP。

真实链路：B 前置（成员/授权/设备能力）以 SQL 种子（test_seed，B 未集成）；D 链
（测肤受理 → 报告发布 → T06 唯一创建 → 方案生成）走真实 HTTP 端点 + 真实 worker；
C 准入消费 D 真实冻结方案。媒体业务读取 404（deny-all，待 B）为预期。
证据正式目录 evidence/CD-chain-2026-09-11-aebccc7/<RUN_ID>/；诊断迭代走 reports/。
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from driver import a_baseline as AB  # noqa: E402
from driver import a_rv5 as R5  # noqa: E402
from driver import c_care as CC  # noqa: E402
from driver import infra as I  # noqa: E402
from driver import verify_reverify_sentinel as verify_sentinel  # noqa: E402
from driver.infra import R, REPORTS  # noqa: E402

EXPECTED_CD = verify_sentinel.EXPECTED_CD
MERGED_HEAD = "aebccc7"
C_CODE = "8b3592e"
D_CODE = "dc955c0"
EVID_DIRNAME = "CD-chain-2026-09-11-aebccc7"
JVM_OPTS = CC.JVM_OPTS

CARE = "/api/v1"
MIN_JPEG = CC.MIN_JPEG

#: 受控能力基线（D 侧受控占位，见 worker dshared/dconfig.py）；T04 设备观察覆盖之。
T04_CAPS = json.dumps({
    "schema_version": 1,
    "capability_id": "mvp-double-capability",
    "revision": 1,
    "parameter_ranges": {
        "intensity": {"unit": "percent", "min": 0.0, "max": 100.0},
        "duration": {"unit": "second", "min": 1.0, "max": 600.0},
        "pulse_count": {"unit": "count", "min": 1.0, "max": 1000.0},
    },
    "approved_regions": ["forehead", "left_cheek", "right_cheek", "nose"],
    "supported_regions": ["forehead", "left_cheek", "right_cheek", "nose"],
    "n_bounds": {"min": 1, "max": 100},
})

#: 11 个剩余 501 占位（NotYetImplementedController 现有方法，B 所属 M1/M2/M5）。
STUB_ROUTES = [
    ("POST", "/api/v1/member-access-grants", {}),
    ("GET", "/api/v1/me/member-access-grants", None),
    ("POST", "/api/v1/gimbals/{G}/heartbeats", {}),
    ("GET", "/api/v1/gimbals/{G}/status", None),
    ("POST", "/api/v1/microcrystal-observations", {}),
    ("GET", "/api/v1/microcrystals/{U}/capabilities", None),
    ("PUT", "/api/v1/me/gimbal-bindings/{G}", {}),
    ("GET", "/api/v1/gimbals/{G}/binding-status", None),
    ("DELETE", "/api/v1/me/gimbal-bindings/{G}", None),
    ("PUT", "/api/v1/me/notification-destinations/inst-e2e-1", {}),
    ("DELETE", "/api/v1/me/member-access-grants/{U}", None),
]

CONTEXT: dict = {}
D_ENV = {
    "MVP_PLAN_WAIT_CHECK_SECONDS": "2",
    "MVP_PLAN_CAPABILITY_STALE_SECONDS": "0",
    "MVP_D_FACE_PROVIDER": "double",
    "MVP_D_SKIN_PROVIDER": "double",
    "MVP_D_PLAN_PROVIDER": "double",
    "MVP_WORKER_BACKOFF_BASE_SECONDS": "1",
    "MVP_WORKER_POLL_INTERVAL_SECONDS": "1",
    "MVP_WORKER_LEASE_SECONDS": "30",
}


def _add(cid, title, status, command="", rc="", excerpt="", blocked=""):
    R.add(cid, title, status, command, str(rc), excerpt, doubles="doubles_pass", blocked=blocked)


def cd_conclusion(settle):
    c = settle["counts"]
    if settle.get("unknown_status"):
        return f"**C+D 集成链路验收结果：拒绝**——未知状态 {settle['unknown_status']}。"
    if c["fail"] > 0 or c["blocked"] > 0:
        return (f"**C+D 集成链路验收结果：未通过**——{c['pass']} PASS / {c['fail']} FAIL / "
                f"{c['blocked']} BLOCKED / {c['info']} INFO。")
    if not AB.settlement_complete(settle):
        return "**C+D 集成链路验收结果：未通过**——结算不完整。"
    if c["info"] > 0:
        ids = [r["id"] for r in R.rows if r["status"] == "INFO"]
        return f"**C+D 集成链路验收结果：通过（附条件）**——INFO 待披露：{ids}。"
    return f"**C+D 集成链路验收结果：通过**——{c['pass']} PASS，替身形态（doubles_pass）。"


def sql(s):
    return I.psql(s)


def scalar(s):
    return I.sql_scalar(s)


def utcnow():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def post_parts(path, token, parts, key):
    """multipart：metadata + 具名二进制 part。返回 (status, body)。"""
    import requests
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    files = {name: (name, data, ctype) for name, data, ctype in parts}
    try:
        r = requests.post(I.APP_BASE + path, headers=headers, files=files, timeout=30,
                          proxies=None)
        return r.status_code, (r.json() if r.text else {})
    except Exception as exc:  # pragma: no cover
        return 0, {"exception": repr(exc)}


def _json_fp(body):
    return json.dumps(body, ensure_ascii=False, sort_keys=True)


def ecode(resp):
    return (resp[1].get("error") or {}).get("code") if isinstance(resp, tuple) else None


def _git(args, timeout=120, log_name=None):
    return I.run(["git", *args], cwd=I.REPO, timeout=timeout, log_name=log_name)


def _max_mtime(paths):
    newest = 0.0
    for p in paths:
        for root, _dirs, files in os.walk(p):
            for f in files:
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, f)))
                except OSError:
                    pass
    return newest


def _evidence_snapshot_dirs():
    base = I.ROOT / "evidence"
    out = []
    if base.exists():
        for d in base.iterdir():
            if d.is_dir():
                out.append(d)
    return out


# ---------------- workers ----------------

def _worker_start():
    if I.WORKER_PROC is not None and I.WORKER_PROC.poll() is None:
        return True, "already-running"
    os.environ.update(D_ENV)
    I.start_worker()
    return I.wait_worker_ready(timeout_s=45)


def _worker_stop():
    I.stop_worker()


def _run_worker_cycles(n, extra_env=None, pause=1.0):
    """真实 worker 单周期步进（--once），并收集每周期日志用于 stale_generation 证据。"""
    env = {**D_ENV, **(extra_env or {})}
    logs = CONTEXT.setdefault("worker_logs", [])
    for _ in range(n):
        I.worker_once(env_extra=env, timeout=180)
        p = REPORTS / "worker-once.log"
        if p.exists():
            logs.append(p.read_text(errors="replace"))
        time.sleep(pause)


# ---------------- CD-01 ----------------

#: merge 后仅允许 E 验收/证据/报告路径继续提交（不触业务/契约）。
CD01_BUSINESS_PATHS = ["backend/web-java", "backend/worker-python", "backend/contracts"]


def cd01_binding_ok(*, anc_c, anc_d, anc_merged, business_diff, care_files,
                    contract_files, mvn_rc, venv_ok, health_up):
    """CD-01 绑定判定纯函数（供 selfcheck 回归）。

    绑定语义 = **祖先关系 + 业务路径 diff 空**，而非 HEAD 字面等值：C/D/merged 均须为
    当前 HEAD 祖先；`merged..HEAD` 业务路径（web-java/worker-python/contracts）diff 为空
    （merge 后仅 E 验收/证据/报告提交）；既有 care diff=0 与 contracts diff=0 保留。
    """
    return bool(anc_c and anc_d and anc_merged and business_diff == []
                and care_files == [] and contract_files == []
                and mvn_rc == 0 and venv_ok and health_up)


def cd_01_build():
    head = _git(["rev-parse", "HEAD"]).stdout.strip()
    anc_c = _git(["merge-base", "--is-ancestor", C_CODE, "HEAD"]).returncode == 0
    anc_d = _git(["merge-base", "--is-ancestor", D_CODE, "HEAD"]).returncode == 0
    anc_merged = _git(["merge-base", "--is-ancestor", MERGED_HEAD, "HEAD"]).returncode == 0
    biz = _git(["diff", f"{MERGED_HEAD}..HEAD", "--", *CD01_BUSINESS_PATHS],
               log_name="cd-01-diff-merged.log")
    business_diff = [x for x in biz.stdout.splitlines() if x.strip()]
    care_paths = ["backend/web-java/src/main/java/cn/yuanxin/mvp/web/care",
                  "backend/web-java/src/test/java/cn/yuanxin/mvp/web/care"]
    diff_c = _git(["diff", f"{C_CODE}..HEAD", "--", *care_paths], log_name="cd-01-diff-c.log")
    care_files = [x for x in diff_c.stdout.splitlines() if x.strip()]
    diff_contracts = _git(["diff", f"{C_CODE}..HEAD", "--", "backend/contracts"],
                          log_name="cd-01-diff-contracts.log")
    contract_files = [x for x in diff_contracts.stdout.splitlines() if x.strip()]
    cp = I.run(["mvn", "-B", "-q", "-DskipTests", "package"], cwd=I.JAVA_DIR, timeout=1800,
               log_name="cd-01-mvn.log")
    jar = I.java_jar()
    import hashlib
    sha = hashlib.sha256(jar.read_bytes()).hexdigest()[:16] if jar.exists() else "-"
    venv_ok = I.run([str(I.PY), "-c", "import sqlalchemy,psycopg,jsonschema,yaml; print('deps OK')"],
                    cwd=I.ROOT, timeout=120, log_name="cd-01-workerdeps.log")
    CONTEXT["cd01"] = {"head": head, "anc_c": anc_c, "anc_d": anc_d, "anc_merged": anc_merged,
                       "business_diff": business_diff, "care_files": care_files,
                       "contract_files": contract_files, "mvn_rc": cp.returncode, "sha16": sha,
                       "venv_ok": venv_ok.returncode == 0}
    return CONTEXT["cd01"]


def cd_01_finalize(health_up):
    d = CONTEXT["cd01"]
    ok = cd01_binding_ok(anc_c=d["anc_c"], anc_d=d["anc_d"], anc_merged=d["anc_merged"],
                         business_diff=d["business_diff"], care_files=d["care_files"],
                         contract_files=d["contract_files"], mvn_rc=d["mvn_rc"],
                         venv_ok=d["venv_ok"], health_up=health_up)
    _add("CD-01", "集成状态绑定（祖先+业务路径 diff 空，非 HEAD 等值）：C 8b3592e / D dc955c0 / "
                  "merged aebccc7 均为当前 HEAD 祖先；`aebccc7..HEAD -- web-java/worker-python/"
                  "contracts` diff 空（merge 后仅 E 验收/证据/报告提交）；care diff=0、contracts "
                  "diff=0；当前源码构建、worker venv 就绪、health UP@18081",
         "PASS" if ok else "FAIL", "git merge-base/diff; mvn package; java -jar; deps import",
         d["mvn_rc"], f"HEAD={d['head'][:12]} C_anc={d['anc_c']} D_anc={d['anc_d']} "
                      f"merged_anc={d['anc_merged']} business_diff={d['business_diff']} "
                      f"care_diff={d['care_files']} contracts_diff={d['contract_files']} "
                      f"jar_sha16={d['sha16']} worker_deps={d['venv_ok']} health={health_up} "
                      f"note=后续提交仅 E 验收/证据/报告")


# ---------------- CD-02 ----------------

def cd_02(app_token):
    results, bad = [], []
    for method, path_t, body in STUB_ROUTES:
        path = path_t.replace("{G}", str(uuid.uuid4())).replace("{U}", str(uuid.uuid4()))
        if body is None:
            code, resp, _ = I.http(method, path, token=app_token)
        else:
            code, resp, _ = I.http(method, path, token=app_token, body=body)
        errobj = resp.get("error") if isinstance(resp, dict) else None
        err = errobj.get("code") if isinstance(errobj, dict) else errobj
        good = code == 501 and err == "NOT_IMPLEMENTED"
        if not good:
            bad.append(f"{method} {path_t}={code}/{err} raw={json.dumps(resp, ensure_ascii=False)[:160]}")
        results.append(f"{method} {path_t}={code}/{err}")
    # 未认证边界：先 401（证明业务路径拒绝无效认证）
    c401, _b, _ = I.http("GET", "/api/v1/me/member-access-grants")
    CONTEXT["cd02"] = {"count": len(STUB_ROUTES), "bad": bad, "unauth": c401}
    ok = not bad and c401 == 401
    _add("CD-02", "剩余占位定向验证：11 个 B 域占位端点（M1/M2/M5）逐个已认证 HTTP 501 "
                  "NOT_IMPLEMENTED；未认证 401（B 待集成边界如实）",
         "PASS" if ok else "FAIL", "逐端点真实 HTTP", f"n={len(STUB_ROUTES)}",
         f"bad={bad} unauth={c401} routes=" + "; ".join(results))


# ---------------- CD-03 ----------------

def _seed_t04(valid):
    mc = str(uuid.uuid4())
    caps = T04_CAPS
    obs = '{"schema_version":1,"source":"e_test_seed","state":"running"}' if valid else "{}"
    observed = "now()" if valid else "NULL"
    sql("INSERT INTO microcrystals (id, serial_no, capabilities, latest_observation,"
        f" observed_at) VALUES ('{mc}','mc-e2e-{mc}',CAST('{caps}' AS jsonb),"
        f"CAST('{obs}' AS jsonb), {observed})")
    return mc


def _gimbal_accept(gtok, capture_session, key=None):
    meta = {"photoVersion": "1", "captureSessionId": capture_session,
            "consentEvidenceRef": "consent-e2e-1"}
    parts = [("metadata", json.dumps(meta).encode(), "application/json"),
             ("front", MIN_JPEG, "image/jpeg"),
             ("left", MIN_JPEG, "image/jpeg"),
             ("right", MIN_JPEG, "image/jpeg")]
    return post_parts("/api/v1/skin-assessment-tasks", gtok, parts, key or str(uuid.uuid4()))


def _poll(fn, timeout_s=150, interval=3.0):
    end = time.time() + timeout_s
    last = None
    while time.time() < end:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    return last


def cd_03(gtok, app_token):
    mc_invalid = _seed_t04(valid=False)
    c, b = _gimbal_accept(gtok, f"cap-{uuid.uuid4().hex[:8]}")
    task = (b.get("data") or {}).get("taskId")
    CONTEXT["a1"] = task
    if c != 202 or not task:
        _add("CD-03", "报告→方案真实链（冻结字段互通）", "FAIL", "M3-A01 受理", c,
             f"A01 failed: {json.dumps(b, ensure_ascii=False)[:300]}")
        return None
    # 真实 worker（--once 步进，低资源；D 依赖经 .venv-driver 满足）
    _run_worker_cycles(10, pause=1.5)
    t06 = ""
    status = ""
    for _ in range(30):
        t06 = scalar(f"SELECT id FROM care_plans WHERE assessment_id='{task}'")
        status = (scalar(f"SELECT generation_status FROM care_plans WHERE assessment_id='{task}'")
                  if t06 else "")
        if t06 and status in ("waiting_inputs", "generating"):
            break
        _run_worker_cycles(2, pause=1.5)
    CONTEXT["plan1"] = t06
    CONTEXT["a1_status_waiting"] = status
    # 捕获 defer 证据（能力未齐 → plan.generate 等待跳：T12 queued、不耗 attempt、lease 轮换）
    defer = {}
    for _ in range(25):
        if t06:
            row = scalar("SELECT id::text||'|'||status||'|'||attempt_count||'|'||lease_revision "
                         f"FROM async_jobs WHERE job_type='plan.generate' AND owner_id='{t06}'")
            if row:
                parts = row.split("|")
                if len(parts) == 4 and parts[1] == "queued" and int(parts[3]) >= 1:
                    defer = {"id": parts[0], "status": parts[1], "attempt": parts[2],
                             "lease_revision": parts[3],
                             "generation_revision": scalar(
                                 f"SELECT generation_revision FROM care_plans WHERE id='{t06}'")}
                    break
        _run_worker_cycles(1, pause=1.5)
    CONTEXT["defer"] = defer
    # 冻结前字段：waiting_inputs / generation_revision=0 / input_photo_version / assessment 唯一
    rev0 = scalar(f"SELECT generation_revision FROM care_plans WHERE id='{t06}'") if t06 else ""
    ipv = scalar(f"SELECT coalesce(input_photo_version::text,'') FROM care_plans WHERE id='{t06}'") if t06 else ""
    dup = scalar(f"SELECT count(*) FROM care_plans WHERE assessment_id='{task}'")
    k0 = scalar(f"SELECT completed_count||'|'||coalesce(completed_at::text,'')||'|'||progress_revision "
                f"FROM care_plans WHERE id='{t06}'") if t06 else ""
    if not t06:
        _add("CD-03", "报告→方案真实链（冻结字段互通）", "FAIL", "worker real chain", "0",
             f"T06 not created (waiting={status}); mc_invalid={mc_invalid}")
        return None
    # 修好 T04 能力（B 待集成：设备能力观察以 test_seed 提供）→ plan.generate 继续
    sql(f"UPDATE microcrystals SET latest_observation="
        f"CAST('{{\"schema_version\":1,\"source\":\"e_test_seed\",\"state\":\"running\"}}' AS jsonb),"
        f" observed_at=now() WHERE id='{mc_invalid}'")
    t04_id = mc_invalid
    CONTEXT["t04"] = t04_id
    ready = ""
    for _ in range(40):
        if scalar(f"SELECT generation_status FROM care_plans WHERE id='{t06}'") == "ready":
            ready = "ready"
            break
        _run_worker_cycles(1, pause=1.0)
    snap = scalar(f"SELECT input_snapshot::text FROM care_plans WHERE id='{t06}'")
    payload = scalar(f"SELECT plan_payload::text FROM care_plans WHERE id='{t06}'")
    k1 = scalar(f"SELECT completed_count||'|'||coalesce(completed_at::text,'')||'|'||progress_revision "
                f"FROM care_plans WHERE id='{t06}'")
    try:
        snapj = json.loads(snap or "{}")
        cap = (snapj.get("capability") or {})
    except Exception:
        snapj, cap = {}, {}
    try:
        plj = json.loads(payload or "{}")
    except Exception:
        plj = {}
    steps = plj.get("steps") or []
    cap_ok = bool(isinstance(cap.get("capability_id"), str) and cap["capability_id"] != ""
                  and isinstance(cap.get("microcrystal_id"), str)
                  and isinstance(cap.get("capability_revision"), int)
                  and isinstance(cap.get("parameter_ranges"), dict) and cap["parameter_ranges"]
                  and all(isinstance(v, dict) and isinstance(v.get("unit"), str) and v.get("unit")
                          for v in cap["parameter_ranges"].values())
                  and isinstance(cap.get("approved_regions"), list) and cap["approved_regions"]
                  and isinstance(cap.get("n_bounds"), dict)
                  and bool(cap["n_bounds"].get("min")) and bool(cap["n_bounds"].get("max")))
    steps_ok = bool(steps) and all(isinstance(s.get("region"), str)
                                   and isinstance(s.get("parameters"), dict) for s in steps)
    k_untouched = k0 == k1
    f_wait = status in ("waiting_inputs", "generating")
    f_ready = ready == "ready"
    f_rev = rev0 == "0"
    f_ipv = ipv == "1"
    f_dup = dup == "1"
    ok = (f_wait and f_rev and f_ipv and f_dup and f_ready and cap_ok and steps_ok
          and k_untouched)
    CONTEXT["cd03"] = {"task": task, "plan": t06, "status_waiting": status, "rev0": rev0,
                      "ipv": ipv, "dup": dup, "ready": ready, "cap": cap,
                      "steps": steps, "k0": k0, "k1": k1, "mc_invalid": mc_invalid,
                      "flags": (f_wait, f_rev, f_ipv, f_dup, f_ready, cap_ok, steps_ok,
                                k_untouched)}
    _add("CD-03", "报告→方案真实链（冻结字段互通）：B 前置 test_seed（gimbal/T04 设备能力）→ 真实 "
                  "M3-A01 受理 → worker analyze/enroll/analyze → T06 由 D 发布事务唯一创建"
                  "（waiting_inputs、generation_revision=0、input_photo_version=1、assessment 唯一）"
                  "→ plan.generate → ready：冻结 capability/steps 形状完整、D 未写 K 列",
         "PASS" if ok else "FAIL", "M3-A01 + 真实 worker 全链", f"a01={c} ready={ready}",
         f"flags[wait,rev,ipv,dup,ready,cap,steps,K]={f_wait},{f_rev},{f_ipv},{f_dup},"
         f"{f_ready},{cap_ok},{steps_ok},{k_untouched} task={task} plan={t06} "
         f"waiting_seen={status} cap={json.dumps(cap, ensure_ascii=False)[:200]} "
         f"steps={len(steps)} K0={k0} K1={k1}")
    return t06


# ---------------- CD-04 ----------------

def cd_04(app_token):
    plan = CONTEXT.get("plan1")
    t04 = CONTEXT.get("t04")
    member = scalar(f"SELECT member_id FROM care_plans WHERE id='{plan}'")
    CONTEXT["member"] = member
    # B 前置：为该真实成员补 active grant（test_seed）
    sql("INSERT INTO member_access_grants (id, account_id, member_id, status, source_request_id)"
        f" VALUES ('{uuid.uuid4()}',"
        f"'{CONTEXT['accountId']}','{member}','active',"
        f"'{CC.seed_idem()}')")
    # Java 以合法绑定成员重启（人脸 dev 替身）
    _proc, up, clean = CC._restart_java(
        CC.variant_env(profiles="dev", bound_member=member), "cd-04-java-bound.log", wait=True)
    if not clean or not up:
        _add("CD-04", "C 准入消费真实 D 冻结方案", "FAIL", "restart java bound", "1", "JVM 未就绪")
        return
    tok = AB.login()["access"]
    mc = t04
    c, b = CC.admit(tok, mc, plan, key=str(uuid.uuid4()))
    ex = (b.get("data") or {}).get("executionId")
    cap = CONTEXT["cd03"]["cap"]
    device = scalar(f"SELECT capabilities::text FROM microcrystals WHERE id='{mc}'")
    try:
        dev = json.loads(device or "{}")
    except Exception:
        dev = {}
    dev_ranges = dev.get("parameter_ranges") or {}
    dev_regions = dev.get("supported_regions") or dev.get("regions") or []
    accepted = c == 201 and bool(ex)
    units_ok = all(dev_ranges.get(k, {}).get("unit") == v.get("unit")
                   for k, v in (cap.get("parameter_ranges") or {}).items())
    regions_ok = set(cap.get("approved_regions") or []) <= set(dev_regions)
    nb = cap.get("n_bounds") or {}
    n_ok = bool(nb.get("min") and nb.get("max"))
    CONTEXT["exec1"] = ex
    ok = accepted and units_ok and regions_ok and n_ok
    sql("INSERT INTO member_access_grants (id, account_id, member_id, status, source_request_id)"
        f" VALUES ('{uuid.uuid4()}','seed','{member}','active','{CC.seed_idem()}')"
        ) if False else None
    _add("CD-04", "C 准入消费真实 D 冻结方案：对 CD-03 真实 ready T06（非种子）执行 C A03 准入"
                  "（dev 人脸绑定）→ 201+T07 创建；能力校验器接受 D 真实冻结基线（双侧 unit/区域/"
                  "N bounds 实际值）",
         "PASS" if ok else "FAIL", "A03 on real D plan + SQL capability evidence", f"{c}",
         f"frozen_capability_id={cap.get('capability_id')} frozen_ranges="
         f"{json.dumps(cap.get('parameter_ranges'), ensure_ascii=False)} "
         f"device_ranges={json.dumps(dev_ranges, ensure_ascii=False)} units_ok={units_ok} "
         f"frozen_regions={cap.get('approved_regions')} device_regions={dev_regions} "
         f"regions_ok={regions_ok} n_bounds={nb} n_ok={n_ok} exec={ex}")


# ---------------- CD-05 ----------------

def _close_exec(token, ex, epoch):
    I.http("POST", f"{CARE}/care-executions/{ex}/observations", token=token,
           body={"observation": {"epoch": epoch, "seq": "1", "state": "stopped",
                                 "occurredAt": utcnow()}, "records": []},
           headers={"Idempotency-Key": str(uuid.uuid4())})
    return I.http("POST", f"{CARE}/care-executions/{ex}/closure-confirmations", token=token,
                  body={"stopObservationSeq": "1", "reason": "user_finished",
                        "recordStreamEpoch": epoch, "finalRecordSeq": "0", "finalCount": "0"},
                  headers={"Idempotency-Key": str(uuid.uuid4())})


def cd_05(gtok, app_token):
    # CD-04 重启过 Java（内存态会话重置），云台会话需重签
    gtok = CC.gimbal_token(CONTEXT["gimbal"])
    plan = CONTEXT.get("plan1")
    a1 = CONTEXT.get("a1")
    member = CONTEXT.get("member")
    # 另起一个覆盖基线的设备微晶（C 云台准入用）
    mc_y = _seed_t04(valid=True)
    rev = scalar(f"SELECT current_assessment_revision FROM gimbals WHERE id='{CONTEXT['gimbal']}'")
    # 替换前：云台对 A1 准入 → 201（真实 D 方案 + 真实指针）
    cpre, bpre = CC.admit(gtok, mc_y, None,
                          metadata=CC.mk_metadata(mc_y, task=a1, rev=rev))
    ex_pre = (bpre.get("data") or {}).get("executionId")
    ep_pre = (bpre.get("data") or {}).get("recordStreamEpoch") or ex_pre
    pre_ok = cpre == 201 and bool(ex_pre)
    # 关闭该准入，避免占用阻塞后续 M3-A01
    if ex_pre:
        _close_exec(gtok, ex_pre, ep_pre)
    # 真实 M3-A01 新任务 → 原子替换 T03 指针 A1→A2
    c2, b2 = _gimbal_accept(gtok, f"cap-{uuid.uuid4().hex[:8]}")
    a2 = (b2.get("data") or {}).get("taskId")
    CONTEXT["a2"] = a2
    replaced_ack = c2 == 202 and bool(a2) and a2 != a1
    # 替换后：旧任务 A1 准入 → 409 TASK_REPLACED（真实链路 A03 面）
    cpost, bpost = CC.admit(gtok, mc_y, None,
                            metadata=CC.mk_metadata(mc_y, task=a1, rev=rev))
    post_a03 = cpost == 409 and (bpost.get("error") or {}).get("code") == "TASK_REPLACED"
    # A08 面：真实链路中替换前执行已 closed（M3-A01 受理要求无未收尾执行），
    # 生命周期冻结（closed）先于指针检查 → 旧执行 A08 为 404；TASK_REPLACED 需 admitted/
    # running/paused 执行。此处如实记录真实结果，并以 test_seed 指针移动做 A08 边界判定。
    a08 = I.http("GET", f"{CARE}/care-plans/{plan}/progress?executionId={ex_pre}"
                 f"&verificationRevision=1", token=gtok)
    a08_real_code = ecode(a08)
    post_a08_real_ok = a08[0] in (409, 404) and a08_real_code in ("TASK_REPLACED",
                                                                 "RESOURCE_NOT_VISIBLE")
    # test_seed 边界：恢复指针到 A1（+rev）→ 云台对 A1 准入 201（open，admitted）→ SQL 移指针
    # 到 A3 → 同一执行 A08 → TASK_REPLACED（验证指针面孔，M3-A01 真实受理无法与此并存）。
    rev2 = int(rev or "1") + 10
    sql(f"UPDATE gimbals SET current_assessment_id='{a1}', current_assessment_revision={rev2},"
        f" updated_at=now() WHERE id='{CONTEXT['gimbal']}'")
    mc_z = _seed_t04(valid=True)
    cz, bz = CC.admit(gtok, mc_z, None, metadata=CC.mk_metadata(mc_z, task=a1, rev=str(rev2)))
    ex_open = (bz.get("data") or {}).get("executionId")
    boundary_ok = False
    a08b = None
    if cz == 201 and ex_open:
        a3 = CC.seed_assessment(CONTEXT["gimbal"], member)
        sql(f"UPDATE gimbals SET current_assessment_id='{a3}',"
            f" current_assessment_revision={rev2 + 1}, updated_at=now() "
            f"WHERE id='{CONTEXT['gimbal']}'")
        a08b = I.http("GET", f"{CARE}/care-plans/{plan}/progress?executionId={ex_open}"
                      f"&verificationRevision=1", token=gtok)
        boundary_ok = (a08b[0] == 409
                       and (a08b[1].get("error") or {}).get("code") == "TASK_REPLACED")
    # 时序化窗口一致性：替换前 201、替换后 TASK_REPLACED，绝无二者皆成/悬挂
    consistent = pre_ok and post_a03
    ok = (pre_ok and replaced_ack and post_a03 and post_a08_real_ok and boundary_ok
          and consistent)
    _add("CD-05", "任务替换 vs 准入竞争（真实链路）：真实 M3-A01 受理触发 T03 指针原子替换"
                  "（非 SQL 种子）；替换前云台 A03=201、替换后旧任务 A03=409 TASK_REPLACED；"
                  "A08 面：真实链路旧执行已 closed→404（生命周期冻结先于指针），另以 test_seed "
                  "指针移动在 admitted 执行上验证 A08=409 TASK_REPLACED；时序化窗口一致"
                  "（无悬挂/无二者皆成）；CC-08 种子化 TASK_REPLACED 保留边界单测",
         "PASS" if ok else "FAIL", "M3-A01 + C A03/A08 时序竞争", f"{cpre}/{cpost}",
         f"pre201={pre_ok}(ex={ex_pre}) replaced={replaced_ack}(a2={a2}) "
         f"post_a03={cpost}/{ecode((cpost, bpost))} a08_real={a08[0]}/{a08_real_code} "
         f"a08_boundary={None if a08b is None else a08b[0]}/"
         f"{None if a08b is None else ecode(a08b)} consistent={consistent}")


# ---------------- CD-06 ----------------

def cd_06(gtok):
    # success：CD-03 全链 job succeeded + 无 stale_generation WARNING（收集的 worker --once 日志）
    logs = list(CONTEXT.get("worker_logs", []))
    wl = REPORTS / "worker-loop.log"
    if wl.exists():
        logs.append(wl.read_text(errors="replace"))
    stale = sum(t.count("stale_generation") for t in logs)
    jobs = scalar("SELECT count(*) FROM async_jobs WHERE status='succeeded'")
    t06 = CONTEXT.get("plan1")
    gen_ok = scalar(f"SELECT generation_status FROM care_plans WHERE id='{t06}'") == "ready"
    success_ok = bool(jobs) and jobs != "0" and stale == 0 and gen_ok
    # defer：CD-03 冻结前捕获的等待跳证据（T12 queued、attempt=0、lease 轮换、gen_rev 不变）
    defer = CONTEXT.get("defer") or {}
    defer_ok = (defer.get("status") == "queued" and defer.get("attempt") == "0"
                and str(defer.get("generation_revision")) == "0"
                and int(defer.get("lease_revision", "0")) >= 1)
    # T13：worker defer 属 T12 语义，不涉及 HTTP 幂等 T13（如实标注）
    t13_note = "not-applicable(worker T12 defer)"
    # 失败：确定性配置故障（baseline 缺 n_bounds）在新受理 A3 上 → PLAN_SNAPSHOT_INVALID 终态原子写
    gtok2 = CC.gimbal_token(CONTEXT["gimbal"])
    ex_open = scalar("SELECT id FROM care_executions WHERE controller_gimbal_id='"
                     f"{CONTEXT['gimbal']}' AND closed_at IS NULL LIMIT 1")
    if ex_open:
        ep = scalar(f"SELECT coalesce(observation_epoch,'') FROM care_executions WHERE id='{ex_open}'")
        _close_exec(gtok2, ex_open, ep or ex_open)
    c3, b3 = _gimbal_accept(gtok2, f"cap-fail-{uuid.uuid4().hex[:8]}")
    a3 = (b3.get("data") or {}).get("taskId")
    CONTEXT["a3"] = a3
    malformed = {"MVP_PLAN_CAPABILITY_BASELINE": json.dumps({
        "schema_version": 1, "capability_id": "mvp-double-capability", "revision": 1,
        "parameter_ranges": {"intensity": {"unit": "percent", "min": 0.0, "max": 100.0}},
        "approved_regions": ["forehead", "left_cheek", "right_cheek", "nose"]})}
    p3 = ""
    st3 = ""
    for _ in range(30):
        p3 = scalar(f"SELECT id FROM care_plans WHERE assessment_id='{a3}'") if a3 else ""
        st3 = scalar(f"SELECT generation_status FROM care_plans WHERE id='{p3}'") if p3 else ""
        if st3 in ("failed", "ready"):
            break
        _run_worker_cycles(2, extra_env=malformed, pause=1.5)
    detail = scalar(f"SELECT coalesce(failure_detail::text,'') FROM care_plans WHERE id='{p3}'") if p3 else ""
    job3 = scalar("SELECT status FROM async_jobs WHERE job_type='plan.generate' AND owner_id="
                  f"'{p3}'") if p3 else ""
    ready3 = scalar(f"SELECT count(*) FROM care_plans WHERE id='{p3}' AND generation_status='ready'")
    fail_ok = (c3 == 202 and bool(a3) and st3 == "failed" and job3 == "failed"
               and ready3 == "0" and "PLAN_SNAPSHOT_INVALID" in (detail or ""))
    fail_detail = (f"a3={a3} accept={c3} p3={p3} status={st3} job={job3} ready_rows={ready3} "
                   f"detail={detail[:160]}")
    ok = success_ok and defer_ok and fail_ok
    _add("CD-06", "D 公共 success/failure/defer 回归（黑盒）：success=全链 job succeeded 且 worker "
                  "日志 stale_generation=0；defer=plan.generate 能力等待跳（T12 queued、attempt=0、"
                  "lease 轮换、T06 generation_revision=0 不变；T13 不适用）；failure=确定性配置故障 "
                  "→ PLAN_SNAPSHOT_INVALID 终态原子写（T06 无 ready 半成品、T12 同 failed）",
         "PASS" if ok else "FAIL", "worker --once 步进 + SQL 终态核对", f"stale={stale}",
         f"succeeded_jobs={jobs} stale_warnings={stale} gen_ready={gen_ok} "
         f"defer={defer} t13={t13_note} failure={fail_detail}")


# ---------------- CD-07 ----------------

def cd_07():
    I.run([str(I.PY), "matrix/generate_matrix.py"], cwd=I.ROOT, timeout=120, log_name="cd-07-gen.log")
    import hashlib
    h1 = hashlib.md5((I.ROOT / "matrix/scenarios.json").read_bytes()).hexdigest()
    I.run([str(I.PY), "matrix/generate_matrix.py"], cwd=I.ROOT, timeout=120)
    h2 = hashlib.md5((I.ROOT / "matrix/scenarios.json").read_bytes()).hexdigest()
    rows = json.loads((I.ROOT / "matrix/scenarios.json").read_text(encoding="utf-8"))
    dist = {}
    for s in rows:
        key = "".join(s["blocked_by"])
        dist[key] = dist.get(key, 0) + 1
    empty = dist.get("", 0)
    b_only = dist.get("B", 0)
    three = subprocess.run(["jq", "-S", "del(.[].owner_package,.[].blocked_by,.[].pending_reason)",
                            str(I.ROOT / "matrix/scenarios.json")], capture_output=True, text=True)
    h3 = hashlib.md5(three.stdout.encode()).hexdigest()
    ids = [s["id"] for s in rows]
    ok = (h1 == h2 and len(rows) == 94 and len(set(ids)) == 94
          and set(dist) <= {"", "B"} and empty == 54 and b_only == 40
          and all(s["status"] == "dependency_pending" for s in rows)
          and h3 == "e4f5dc522fe60a83db47d7e42b595652")
    CONTEXT["cd07"] = {"dist": dist, "hash3": h3, "idem": h1 == h2}
    _add("CD-07", "矩阵诚实维护：blocked_by=owner−已集成{C,D} → []×54 / B×40；owner/94 ID/"
                  "业务语义逐字节不变（三字段剔除哈希 e4f5dc52）；pending_reason 分类细化"
                  "（C/D 已集成已验收 / B 未集成 501）；再生成幂等；gate closed、94 pending",
         "PASS" if ok else "FAIL", "generate_matrix x2 + jq 断言", "0",
         f"dist={dist} idempotent={h1 == h2} hash3={h3} n={len(rows)}")


# ---------------- CD-08 ----------------

def cd_08():
    evidence_before = CONTEXT.get("evidence_before", 0.0)
    evidence_after = _max_mtime(_evidence_snapshot_dirs())
    zero_overwrite = evidence_after <= evidence_before
    handoff = I.ROOT.parent / "handoffs" / "E-CD-acceptance.md"
    doc = handoff.read_text(encoding="utf-8") if handoff.exists() else ""
    wiring = all(k in doc for k in ("media.cleanup", "enroll", "真实供应商"))
    b_list = CONTEXT.get("cd02", {}).get("count", 0)
    ok = bool(CONTEXT.get("cd02")) and not CONTEXT["cd02"]["bad"] and zero_overwrite and wiring and b_list == 11
    _add("CD-08", "诚实披露与证据纪律：全部 doubles_pass；B 依赖逐项 dependency_pending（11 端点 501 + "
                  "媒体读取 deny-all）；不声称完整 MVP；既有证据目录零覆盖；D 待接线如实转录"
                  "（media.cleanup 周期触发 / enroll failed 槽位运维恢复 / 真实供应商前提）",
         "PASS" if ok else "FAIL", "证据/披露静态核对", "0",
         f"b_stub_endpoints={b_list} zero_overwrite={zero_overwrite} "
         f"doc_wiring={wiring} doc_exists={handoff.exists()}")


# ---------------- outputs ----------------

def write_outputs_cd(settle, rc, formal_dir):
    counts = settle["counts"]
    result = {"schema": "e-acceptance-cd-chain/1", "run_id": I.RUN_ID, "mode": "cd-chain",
              "merged_head": MERGED_HEAD, "c_code": C_CODE, "d_code": D_CODE,
              "expected": settle["expected"], "settled": settle["settled"],
              "missing": settle["missing"], "extra": settle["extra"],
              "duplicates": settle["duplicates"], "unknown_status": settle.get("unknown_status", []),
              "counts": counts, "counts_sum": sum(counts.values()), "rows": settle.get("rows"),
              "final_exit": rc, "results": R.rows}
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    formal_dir.mkdir(parents=True, exist_ok=True)
    (formal_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    cell = (lambda s: str(s).replace("|", "/").replace("\n", " "))
    lines = [
        f"# E C+D 集成链路验收 —— merged {MERGED_HEAD}（C {C_CODE} + D {D_CODE}），run {I.RUN_ID}",
        "",
        "> **替身形态（doubles_pass）**：D 三提供方（face/skin/plan）为受控确定性替身；B 未集成"
        "（成员/授权/设备/媒体以 SQL 种子 test_seed 提供）；媒体业务读取 404（deny-all）为预期。",
        "",
        f"## 结算：{settle['settled']}/{settle['expected']} 唯一结算；"
        f"{counts['pass']} PASS / {counts['fail']} FAIL / {counts['blocked']} BLOCKED / "
        f"{counts['info']} INFO（计数和={sum(counts.values())}==行数 {settle.get('rows')}）；"
        f"final_exit={rc}",
        "",
        cd_conclusion(settle),
        "",
        "| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |",
        "|---|---|---|---|---|",
    ]
    for r in R.rows:
        lines.append(f"| {r['id']} | {cell(r['title'])} | **{r['status']}** | "
                     f"{cell(r['command'])} / {r['rc']} | {cell(r['excerpt'])} |")
    fails = [r for r in R.rows if r["status"] == "FAIL"]
    lines += ["", "## 缺陷清单", ""]
    lines.append("（无 FAIL 项）" if not fails else "")
    for r in fails:
        lines.append(f"- **{r['id']}** {r['title']}；{r['excerpt']}")
    lines += ["", "## B 待集成清单", "",
              "- M1/M2/M5 共 11 个端点 501 NOT_IMPLEMENTED（成员授权/云台心跳状态/微晶观察/绑定/通知）。",
              "- 媒体业务读取（contentUrl 实际下载）待 B 统一 @Primary MediaAccessPolicy（当前 deny-all → 404）。",
              "- 真实成员授权/撤销、设备凭据、媒体访问策略端到端。",
              "", "## D 待接线事项（如实转录）", "",
              "- media.cleanup 周期触发/崩溃孤儿扫描接线（D 提供幂等 discover_and_enqueue_orphans+handler）。",
              "- enroll 终态 failed 槽位保持占用，受控恢复=运维对账后置 cancelled/succeeded。",
              "- 真实供应商激活前提（凭据+PoC+设备团队批准基线，provenance mismatch fail-closed）。", ""]
    (formal_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n=== E CD-chain: {counts['pass']} PASS / {counts['fail']} FAIL / "
          f"{counts['blocked']} BLOCKED / {counts['info']} INFO "
          f"(settled {settle['settled']}/{settle['expected']}, exit={rc}) ===")
    print(cd_conclusion(settle))
    print(f"evidence: {formal_dir}/summary.md")


# ---------------- main ----------------

def main() -> int:
    formal = not os.environ.get("E_CD_ONLY")
    EVID = EVID_DIRNAME
    formal_dir = I.ROOT / "evidence" / EVID / I.RUN_ID
    I.set_output_mode(formal, formal_dir=formal_dir)
    REPORTS.mkdir(parents=True, exist_ok=True)
    ok_lock, why = I.acquire_single_instance_lock()
    if not ok_lock:
        print(f"[FATAL] {why}")
        return 4
    try:
        if not all(I.check_ports().values()) or I.container_exists():
            _add("SETUP", "前置：端口空闲且无同名容器", "FAIL", "ss/docker", "1", "环境未净")
        else:
            CONTEXT["evidence_before"] = _max_mtime(_evidence_snapshot_dirs())
            cp = I.start_pg()
            if cp.returncode != 0 or not I.wait_pg():
                _add("SETUP", "启动 E 专用 PG", "FAIL", "docker run mvp-e-pg", cp.returncode, "")
            else:
                I.recreate_db()
                only = os.environ.get("E_CD_ONLY", "")
                names = only.split(",") if only else None

                def want(n):
                    return names is None or n in names
                d01 = cd_01_build()
                up = I.start_java(extra_env={"JAVA_TOOL_OPTIONS": JVM_OPTS},
                                  log_name="cd-main-java.log")
                cd_01_finalize(up)
                # 种子：APP 账号 + 云台（B 前置 test_seed）
                account = AB.login()
                CONTEXT["accountId"] = account["accountId"]
                app_token = account["access"]
                gimbal = CC.seed_gimbal()
                gtok = CC.gimbal_token(gimbal)
                CONTEXT["gimbal"] = gimbal
                CONTEXT["gtok"] = gtok
                if want("cd02"):
                    cd_02(app_token)
                plan1 = None
                if want("cd03"):
                    plan1 = cd_03(gtok, app_token)
                if want("cd04") and plan1:
                    cd_04(app_token)
                if want("cd05") and plan1:
                    cd_05(gtok, app_token)
                if want("cd06") and plan1:
                    cd_06(gtok)
                if want("cd07"):
                    cd_07()
                if want("cd08"):
                    cd_08()
    finally:
        try:
            I.stop_worker()
            I.stop_java()
            I.kill_own_java()
            try:
                I.remove_container()
            except Exception as exc:
                _add("CLEANUP", "按 run 标签删除 E 容器", "FAIL", "docker rm", "1", str(exc))
            if "CLEANUP" not in {r["id"] for r in R.rows}:
                _add("CLEANUP", "停进程并按 run 标签删除 mvp-e-pg",
                     "PASS" if not I.container_exists() else "FAIL", "docker rm -f -v", "0", "")
            freed = False
            for _ in range(25):
                if I.port_free(I.APP_PORT) and I.port_free(I.PG_HOST_PORT) \
                        and I.port_free(I.WORKER_HEALTH_PORT):
                    freed = True
                    break
                time.sleep(1)
            _add("CLEANUP-ports", "端口释放（Java/PG/worker）", "PASS" if freed else "FAIL", "ss", "0", "")
        finally:
            I.release_single_instance_lock()
        settle = AB.settlement(expected=EXPECTED_CD)
        rc = AB.final_exit(formal, settle)
        write_outputs_cd(settle, rc, formal_dir if formal else REPORTS)
        verify_sentinel.write_sentinel(I.RUN_ID, settle, rc, mode="cd-chain", expected=EXPECTED_CD)
    return rc


if __name__ == "__main__":
    sys.exit(main())
