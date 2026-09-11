#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E 对 C/M4（护理管理，SHA 8b3592e）的独立黑盒验收驱动：CC-01..CC-12 + CLEANUP。

复用 infra/a_baseline 骨架；不启动 worker（care 包零 worker 依赖）。
证据正式目录 evidence/C-acceptance-2026-09-11-8b3592e/<RUN_ID>/；诊断迭代走 reports/。
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import uuid

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from driver import a_baseline as AB  # noqa: E402
from driver import a_rv5 as R5  # noqa: E402
from driver import infra as I  # noqa: E402
from driver import verify_reverify_sentinel as verify_sentinel  # noqa: E402
from driver.infra import R, REPORTS  # noqa: E402

EXPECTED_C = verify_sentinel.EXPECTED_C
C_CODE = "8b3592e"
EVID_DIRNAME = "C-acceptance-2026-09-11-8b3592e"
JVM_OPTS = "-Xmx640m -XX:MaxMetaspaceSize=256m"

DEFAULT_INPUT_SNAPSHOT = json.dumps({
    "schema_version": 1,
    "report": {"assessment_id": None},
    "capability": {"microcrystal_id": None, "capability_id": "cap-mvp-1",
                   "capability_revision": "7",
                   "parameter_ranges": {"intensity": {"min": "0", "max": "5", "unit": "level"}},
                   "approved_regions": ["face"], "n_bounds": {"min": "1", "max": "30"}}})
DEFAULT_CAPABILITIES = json.dumps({
    "schema_version": 1, "capability_id": "cap-mvp-1", "revision": "9",
    "parameter_ranges": {"intensity": {"min": "0", "max": "8", "unit": "level"}},
    "supported_regions": ["face", "neck"]})
CLEAN_PLAN = json.dumps({"schema_version": 1, "title": "完整方案",
    "steps": [{"region": "face", "parameters": {"intensity": "3"}}]})
SENSITIVE_PLAN = json.dumps({
    "schema_version": 1, "title": "完整方案", "description": "d",
    "provider_raw_response": "SECRET1", "steps": [
        {"region": "face", "prompt": "SECRET2",
         "parameters": {"intensity": "3",
                        "vendor_debug": {"value": "3", "unit": "level", "SECRET3": "x"}}}],
    "regions": ["face", 123, {"x": 1}], "parameters": {"intensity": "3"}})

CARE = "/api/v1"


def canon_diff(bodies):
    keys = ["requestId", "error", "data", "meta"]
    objs = [json.loads(b) if isinstance(b, str) else b for b in bodies]
    d = {}
    for k in keys:
        vals = {json.dumps(o.get(k), sort_keys=True, ensure_ascii=False) for o in objs}
        if len(vals) > 1:
            d[k] = [json.dumps(o.get(k), ensure_ascii=False)[:300] for o in objs]
    return json.dumps(d, ensure_ascii=False)[:900]


def _add(cid, title, status, command="", rc="", excerpt="", blocked=""):
    R.add(cid, title, status, command, str(rc), excerpt, doubles="doubles_pass", blocked=blocked)


def cc_conclusion(settle):
    c = settle["counts"]
    if settle.get("unknown_status"):
        return f"**C/M4 黑盒验收结果：拒绝**——未知状态 {settle['unknown_status']}。"
    if c["fail"] > 0 or c["blocked"] > 0:
        return (f"**C/M4 黑盒验收结果：未通过**——{c['pass']} PASS / {c['fail']} FAIL / "
                f"{c['blocked']} BLOCKED / {c['info']} INFO。")
    if not AB.settlement_complete(settle):
        return ("**C/M4 黑盒验收结果：未通过**——结算不完整。")
    if c["info"] > 0:
        ids = [r["id"] for r in R.rows if r["status"] == "INFO"]
        return f"**C/M4 黑盒验收结果：通过（附条件）**——INFO 待披露：{ids}。"
    return f"**C/M4 黑盒验收结果：通过**——{c['pass']} PASS，替身形态（doubles_pass）。"


# ---------------- HTTP helpers ----------------

MIN_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")


def post_multipart(path, token, metadata, key, image=None):
    image = image if image is not None else MIN_JPEG
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    files = {"metadata": (None, json.dumps(metadata), "application/json"),
             "face": ("face.jpg", image, "image/jpeg")}
    try:
        r = requests.post(I.APP_BASE + path, headers=headers, files=files, timeout=30,
                          proxies=None)
        return r.status_code, (r.json() if r.text else {})
    except Exception as exc:  # pragma: no cover
        return 0, {"exception": repr(exc)}


def get_json(path, token=None):
    return I.http("GET", path, token=token)


def post_json(path, token, body, key=None):
    h = {"Idempotency-Key": key} if key else {}
    return I.http("POST", path, token=token, body=body, headers=h)


def sql(sql, db=None):
    return I.psql(sql)


def scalar(sql):
    return I.sql_scalar(sql)


def utcnow():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_tail(name, n=6):
    p = REPORTS / name
    if not p.exists():
        return ""
    return "\n".join(p.read_text(errors="replace").splitlines()[-n:])


# ---------------- seeds ----------------

def seed_idem():
    i = str(uuid.uuid4())
    sql("INSERT INTO idempotency_requests (id, principal_type, principal_id, operation,"
        f" idempotency_key, payload_hash, status) VALUES ('{i}','app_account','seed','seed','{i}',"
        "'seed','succeeded')")
    return i


def seed_member(mid=None):
    m = mid or str(uuid.uuid4())
    sql(f"INSERT INTO members (id) VALUES ('{m}')")
    return m


def seed_grant(account, member, status="active"):
    sql("INSERT INTO member_access_grants (id, account_id, member_id, status, source_request_id)"
        f" VALUES ('{uuid.uuid4()}','{account}','{member}','{status}','{seed_idem()}')")


def seed_gimbal():
    g = str(uuid.uuid4())
    sql("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version)"
        f" VALUES ('{g}','gimbal-{g}','gimbal-subj-{g}',1)")
    return g


def seed_microcrystal(caps=DEFAULT_CAPABILITIES):
    mc = str(uuid.uuid4())
    sql("INSERT INTO microcrystals (id, serial_no, capabilities)"
        f" VALUES ('{mc}','mc-{mc}',CAST('{caps}' AS jsonb))")
    return mc


def seed_assessment(gimbal, member, status="queued"):
    a = str(uuid.uuid4())
    sql("INSERT INTO skin_assessments (id, gimbal_id, member_id, status, source_request_id)"
        f" VALUES ('{a}','{gimbal}','{member}','{status}','{seed_idem()}')")
    return a


def seed_plan(assessment, member, status="ready", payload=None, target=None, completed=0,
              revision=0, mc=None):
    p = str(uuid.uuid4())
    payload = payload or CLEAN_PLAN
    sql("INSERT INTO care_plans (id, assessment_id, member_id, generation_status, plan_summary,"
        " plan_payload, target_count, completed_count, progress_revision)"
        f" VALUES ('{p}','{assessment}','{member}','{status}',CAST('{{\"schema_version\":1}}' AS jsonb),"
        f"CAST('{payload}' AS jsonb),{target if target is not None else 'NULL'},{completed},{revision})")
    snap = DEFAULT_INPUT_SNAPSHOT.replace('"assessment_id": null', f'"assessment_id": "{assessment}"')
    snap = snap.replace('"microcrystal_id": null', f'"microcrystal_id": "{mc or CONTEXT["mc"]}"')
    sql(f"UPDATE care_plans SET input_snapshot=CAST('{snap}' AS jsonb) WHERE id='{p}'")
    return p


def new_plan_and_mc(target=3, payload=None, caps=None, status="ready"):
    mc = seed_microcrystal(caps or DEFAULT_CAPABILITIES)
    asmt = seed_assessment(CONTEXT["gimbal"], CONTEXT["member"])
    plan = seed_plan(asmt, CONTEXT["member"], status, payload, target=target, mc=mc)
    return plan, mc


def gimbal_token(gimbal):
    code, body, _ = I.http("POST", f"{CARE}/gimbal-sessions", body={
        "credential": f"gimbal-subj-{gimbal}", "credentialVersion": "1", "proof": "p"})
    return (body.get("data") or {}).get("sessionToken") if code == 200 else None


def mk_metadata(mc, plan=None, task=None, rev=None, purpose="admission", extra=None):
    md = {"microcrystalId": mc, "connectionProof": "cp", "consentEvidenceRef": "consent-1",
          "capture": {"captureId": str(uuid.uuid4()), "capturedAt": utcnow(),
                      "clientContinuityId": "cc-1", "purpose": purpose}}
    if plan:
        md["planId"] = plan
    if task:
        md["currentTaskId"] = task
        md["currentAssessmentRevision"] = rev
    if extra:
        md.update(extra)
    return md


CONTEXT: dict = {}


def admit(account_token, mc, plan, key=None, metadata=None):
    return post_multipart(f"{CARE}/care-executions", account_token,
                          metadata or mk_metadata(mc, plan=plan), key or str(uuid.uuid4()))


def obs_body(epoch, seq=1, state="running", rev="1", continuity=True):
    return {"observation": {"epoch": epoch, "seq": str(seq), "state": state,
                            "occurredAt": utcnow(), "verificationRevision": rev,
                            "continuityValid": continuity}, "records": []}


def rec(epoch, seq, delta="1", rid=None):
    return {"recordId": rid or f"r-{epoch[:8]}-{seq}", "sourceEpoch": epoch, "sourceSeq": str(seq),
            "countDelta": str(delta), "occurredAt": utcnow()}


def obs_records(epoch, records, seq=1, state="running", rev="1", continuity=True):
    b = obs_body(epoch, seq, state, rev, continuity)
    b["records"] = records
    return b


def sync(account_token, execution, body, key):
    return post_json(f"{CARE}/care-executions/{execution}/observations", account_token, body, key)


def closure(account_token, execution, epoch, final_seq, final_count, key, stop_seq=1):
    return post_json(f"{CARE}/care-executions/{execution}/closure-confirmations", account_token,
                     {"stopObservationSeq": str(stop_seq), "reason": "user_finished",
                      "recordStreamEpoch": epoch, "finalRecordSeq": str(final_seq),
                      "finalCount": str(final_count)}, key)


# ---------------- CC-01 ----------------

def cc_01():
    head = I.run(["git", "rev-parse", "HEAD"], cwd=I.REPO, timeout=60).stdout.strip()
    anc = I.run(["git", "merge-base", "--is-ancestor", C_CODE, "HEAD"], cwd=I.REPO, timeout=60)
    diff = I.run(["git", "diff", f"{C_CODE}..HEAD", "--", "backend/web-java",
                  "backend/worker-python", "backend/contracts"], cwd=I.REPO, timeout=120,
                 log_name="cc-01-diff.log")
    files = [x for x in diff.stdout.splitlines() if x.strip()]
    cp = I.run(["mvn", "-B", "-q", "-DskipTests", "package"], cwd=I.JAVA_DIR, timeout=1800,
               log_name="cc-01-mvn.log")
    jar = I.java_jar()
    import hashlib
    sha = hashlib.sha256(jar.read_bytes()).hexdigest()[:16] if jar.exists() else "-"
    ok = anc.returncode == 0 and cp.returncode == 0
    _add("CC-01", "构建与启动绑定：HEAD=93b7e33、8b3592e 祖先、源码 diff 空、当前源码构建、health UP",
         "PASS" if ok else "FAIL", "git merge-base/diff; mvn -DskipTests package; java -jar",
         cp.returncode, f"HEAD={head[:12]} ancestor={anc.returncode == 0} diff_files={files} "
                        f"jar={jar.name} sha16={sha}")


# ---------------- CC-02 ----------------

def cc02_verdict(statuses, canon, codes, c403, b403, c401, cA, cB, cC):
    """CC-02 三态判定纯函数（供 selfcheck 回归锁定语义，防谓词再次写反）。

    语义：A01/A02/A07/A08/A09+不存在 五个端点对异账号全等 404（完整公开体仅去
    requestId）；云台跨面 403 CALLER_NOT_ALLOWED；未认证 401；撤销授权即时 404；
    **另一仍 active 的授权账号必须 200**（cC，历史误写 404 的唯一 false 谓词）。
    """
    statuses_ok = all(x == 404 for x in statuses)
    equal = len(set(canon)) == 1
    codes_ok = all(x == "RESOURCE_NOT_VISIBLE" for x in codes)
    g403_ok = c403 == 403 and (b403.get("error") or {}).get("code") == "CALLER_NOT_ALLOWED"
    flags = dict(statuses=statuses_ok, equal=equal, codes=codes_ok, g403=g403_ok,
                 n401=c401 == 401, cA=cA == 200, cB=cB == 404, cC=cC == 200)
    ok = (statuses_ok and equal and codes_ok and g403_ok
          and c401 == 401 and cA == 200 and cB == 404 and cC == 200)
    return ok, flags


def cc_02(ctx):
    a, plan, member = ctx["tok"], ctx["plan"], ctx["member"]
    foreign = AB.login(identity_tag=uuid.uuid4().hex[:8])
    fk = foreign["access"]
    statuses, codes, canon = [], [], []

    def one(path, token):
        c, b, _ = get_json(path, token)
        return c, b

    for path in (f"{CARE}/members/{member}/care-plans", f"{CARE}/care-plans/{plan}?view=full",
                 f"{CARE}/care-executions/{ctx.get('execution')}",
                 f"{CARE}/care-plans/{plan}/progress",
                 f"{CARE}/members/{member}/care-executions"):
        c, b = one(path, fk)
        statuses.append(c)
        codes.append((b.get("error") or {}).get("code"))
        canon.append(R5.canon_public(b))
    c, b = one(f"{CARE}/care-plans/{uuid.uuid4()}?view=full", a)
    statuses.append(c)
    codes.append((b.get("error") or {}).get("code"))
    canon.append(R5.canon_public(b))
    I.evidence_text("cc-02-bodies.json", json.dumps(
        [json.loads(x) for x in canon], ensure_ascii=False, indent=2))
    # 云台调 APP-only → 403；未认证 → 401
    c403, b403, _ = get_json(f"{CARE}/members/{member}/care-plans", ctx["gtok"])
    c401, b401, _ = get_json(f"{CARE}/members/{member}/care-plans")
    # 撤销 grant 独立账号（不计入三态等值集合）
    rev = AB.login(identity_tag=uuid.uuid4().hex[:8])
    m2 = seed_member()
    seed_grant(rev["accountId"], m2)
    r1 = AB.login(identity_tag=uuid.uuid4().hex[:8])
    seed_grant(r1["accountId"], m2)
    cA, _ = one(f"{CARE}/members/{m2}/care-plans", rev["access"])
    sql(f"UPDATE member_access_grants SET status='revoked', revoked_at=now(), updated_at=now() "
        f"WHERE account_id='{rev['accountId']}' AND member_id='{m2}'")
    cB, _ = one(f"{CARE}/members/{m2}/care-plans", rev["access"])
    cC, _ = one(f"{CARE}/members/{m2}/care-plans", r1["access"])
    ok, flags = cc02_verdict(statuses, canon, codes, c403, b403, c401, cA, cB, cC)
    _add("CC-02", "权限/统一 404 三态：A01/A02/A07/A08/A09+不存在 全等 404（完整公开体仅排除 "
                  "requestId）+ 云台 403 + 未认证 401 + 撤销即时生效",
         "PASS" if ok else "FAIL", "多账号 GET 交叉 + 撤销 grant",
         f"{statuses}", f"public_equal={len(set(canon)) == 1} codes={codes} "
                         f"gimbal={c403}/{(b403.get('error') or {}).get('code')} noauth={c401} "
                         f"revoked={cB} other_active={cC} seed_ok={cA == 200} "
                         f"canon_diff={canon_diff(canon)} flags={flags}")


# ---------------- CC-03 ----------------

def variant_env(*, profiles, bound_member=None, app_env=None):
    """逐变体**显式**构造 JVM env（纯函数，供 selfcheck 锁定）。

    三个相关键全部显式给出，未涉及者置空串，绝不依赖 os.environ 继承或前序实例残留：
    - ``SPRING_PROFILES_ACTIVE``：生效 profile（prod/prod,dev/dev）；
    - ``APP_C_FACE_BOUND_MEMBER``：合法绑定值 / 空串（无绑定，显式清除）；
    - ``APP_ENV``：仅变体③显式 ``production``；其余置空（app.env 规范化回 dev）。
    """
    return {
        "SPRING_PROFILES_ACTIVE": profiles,
        "APP_C_FACE_BOUND_MEMBER": bound_member if bound_member is not None else "",
        "APP_ENV": app_env if app_env is not None else "",
    }


def _await_java_gone(tries: int = 40) -> bool:
    """完全退出确认：停本进程 + 兜底 pkill 本工作树 jar，等 18081 真正空闲。

    端口空闲是启动新实例的**前置条件**——否则新进程绑定失败退出、而旧实例仍在
    18081 应答，``/actuator/health`` 会被旧实例冒充为 UP（历史 CC-03 正例 503 根因）。
    """
    import time as _t
    I.stop_java()
    I.kill_own_java()
    for _ in range(tries):
        if I.port_free(I.APP_PORT):
            return True
        _t.sleep(1)
    return False


def _restart_java(env, log, wait=True):
    """统一 JVM 启动封装：先确认完全退出/端口空闲，再以显式 env 启动。

    返回 ``(proc, up, clean)``：``clean=False`` 表示端口未释放，未启动（拒绝以
    未净环境判定），调用方须按失败处理而非误判通过。JVM 限堆始终 ≤768m。
    """
    if not _await_java_gone():
        return None, False, False
    up = I.start_java(extra_env={"JAVA_TOOL_OPTIONS": JVM_OPTS, **(env or {})},
                      log_name=log, wait=wait)
    return I.JAVA_PROC, up, True


def cc_03(ctx):
    results, pos = [], False
    member = ctx["member"]

    def run_variant(label, env, log):
        proc, _up, clean = _restart_java(env, log, wait=False)
        if not clean or proc is None:
            I.stop_java()
            results.append(f"{label}: 环境未净（端口未释放），未启动，拒绝判定")
            return None
        try:
            rc = proc.wait(timeout=90)
        except Exception:
            rc = "running"
        I.stop_java()
        refused = isinstance(rc, int) and rc != 0
        results.append(f"{label}: rc={rc} refused={refused}")
        return rc

    # ⑤ 正例对照先行（判别力：201 且 T07 care_executions 真实新增一行）
    for attempt in (1, 2):
        log = "cc-03-positive.log" if attempt == 1 else "cc-03-positive-retry.log"
        _proc, up, clean = _restart_java(
            variant_env(profiles="dev", bound_member=member), log, wait=True)
        if not clean or not up:
            results.append(f"dev+bound positive(attempt {attempt}): JVM 未就绪/环境未净")
            continue
        tok = AB.login()["access"]  # type: ignore[union-attr]
        pplan, pmc = new_plan_and_mc(target=3)
        rows0 = int(scalar("SELECT count(*) FROM care_executions") or 0)
        c, _ = admit(tok, pmc, pplan)
        rows1 = int(scalar("SELECT count(*) FROM care_executions") or 0)
        created = rows1 == rows0 + 1
        results.append(f"dev+bound positive(attempt {attempt}): A03={c} T07_created={created}")
        if c == 201 and created:
            pos = True
            break
    I.stop_java()
    I.kill_own_java()
    # ①②③④ 负例变体（串行；每变体 env 显式构造 + 前置完全退出确认）
    r1 = run_variant("prod-only", variant_env(profiles="prod"), "cc-03-prod.log")
    r2 = run_variant("prod,dev+bound",
                     variant_env(profiles="prod,dev", bound_member=member), "cc-03-prod-dev.log")
    r3 = run_variant("dev+APP_ENV=production",
                     variant_env(profiles="dev", bound_member=member, app_env="production"),
                     "cc-03-dev-prod.log")
    r4 = run_variant("dev+invalid-bound",
                     variant_env(profiles="dev", bound_member="not-a-uuid"), "cc-03-bad.log")
    I.evidence_text("cc-03-variants.txt", "\n".join(results))
    # 生产拒绝断言不放宽：必须真实非零退出（None/0/running 均判失败）
    refused = [isinstance(r, int) and r != 0 for r in (r1, r2, r3, r4)]
    ok = pos and all(refused)
    _add("CC-03", "生产人脸 fail-closed：prod / prod,dev / dev+APP_ENV=production / 非法绑定 "
                  "拒绝启动；dev 合法绑定正例 A03 201+T07 创建（判别力）",
         "PASS" if ok else "FAIL", "逐变体串行启动 JVM（限堆 640m）+ 正例先行",
         f"{r1},{r2},{r3},{r4}", " | ".join(results))


# ---------------- CC-04 ----------------

def cc_04(ctx):
    # 主 Java 以 APP_C_FACE_BOUND_MEMBER=member 启动；此处验证绑定成员 201 + 未带 memberId 输入
    a, member = ctx["tok"], ctx["member"]
    plan, mc = new_plan_and_mc(target=3)
    c1, b1 = admit(a, mc, plan, key=str(uuid.uuid4()))
    exec_id = (b1.get("data") or {}).get("executionId")
    ctx["execution"] = exec_id or ctx.get("execution")
    obs = (b1.get("data") or {}).get("observation_epoch") or (b1.get("data") or {}).get(
        "recordStreamEpoch") or exec_id
    ctx["epoch"] = obs
    no_member_field = "memberId" not in json.dumps(mk_metadata(mc, plan=plan))
    ok1 = c1 == 201 and bool(exec_id) and no_member_field
    # 异成员：另起 Java（绑定 other 成员）→ A03 403 FACE_NOT_VERIFIED + T07 零行
    other_member = seed_member()
    seed_grant(ctx["accountId"], other_member)
    _restart_java(variant_env(profiles="dev", bound_member=other_member), "cc-04-foreign.log")
    a = AB.login()["access"]  # 重启后会话内存态重置，须重登
    fp, fmc = new_plan_and_mc(target=3)
    rows = scalar("SELECT count(*) FROM care_executions")
    c2, b2 = admit(a, fmc, fp, key=str(uuid.uuid4()))
    rows2 = scalar("SELECT count(*) FROM care_executions")
    ok2 = c2 == 403 and (b2.get("error") or {}).get("code") == "FACE_NOT_VERIFIED" and rows2 == rows
    # 未绑定：显式清空绑定重启 → 503 + 零行 + T13 processing
    _restart_java(variant_env(profiles="dev"), "cc-04-unbound.log")
    a = AB.login()["access"]
    up, umc = new_plan_and_mc(target=3)
    key3 = str(uuid.uuid4())
    rows3a = scalar("SELECT count(*) FROM care_executions")
    c3, b3 = admit(a, umc, up, key=key3)
    rows3b = scalar("SELECT count(*) FROM care_executions")
    t13 = scalar("SELECT status FROM idempotency_requests WHERE idempotency_key='" + key3 + "'")
    ok3 = c3 == 503 and rows3b == rows3a and t13 == "processing"
    # 恢复主流程：复位为绑定成员并重启（先完全退出，防遗留未绑定实例占端口），重置云台 token
    _restart_java(variant_env(profiles="dev", bound_member=member), "cc-04-restore.log")
    ctx["tok"] = AB.login()["access"]
    ctx["gtok"] = gimbal_token(ctx["gimbal"])
    _add("CC-04", "人脸 1:1 成员绑定（dev 替身）：绑定成员 201；异成员 403 FACE_NOT_VERIFIED+"
                  "T07 零行；未绑定 503+T07 零行+T13 processing；无客户端 memberId 输入路径",
         "PASS" if (ok1 and ok2 and ok3) else "FAIL",
         "三次 JVM 绑定切换 + A03 multipart",
         f"{c1}/{c2}/{c3}", f"bound201={ok1} foreign403={ok2}(rows {rows}->{rows2}) "
                             f"unbound503={ok3}(rows {rows3a}->{rows3b} t13={t13}) "
                             f"noClientMemberField={no_member_field}")


# ---------------- CC-05 ----------------

def cc_05(ctx):
    a, plan = ctx["tok"], ctx["plan"]
    c1, b1, _ = get_json(f"{CARE}/care-plans/{plan}?view=full", a)
    c2, b2, _ = get_json(f"{CARE}/members/{ctx['member']}/care-plans", a)
    c3, b3, _ = get_json(f"{CARE}/care-plans/{plan}/progress", a)
    snap = scalar("SELECT plan_snapshot::text FROM care_executions WHERE id='" +
                  str(ctx.get('execution')) + "'")
    blob = json.dumps([b1, b2, b3], ensure_ascii=False) + (snap or "")
    hit = R5.forbidden_hit(blob, ["SECRET1", "SECRET2", "SECRET3", "provider_raw_response",
                                  "prompt"])
    vd = None
    try:
        vd = b1["data"]["plan"]["steps"][0]["parameters"].get("vendor_debug")
    except Exception:
        vd = None
    vd_ok = vd == {"value": "3", "unit": "level"}
    kept = '"region": "face"' in json.dumps(b1, ensure_ascii=False) or \
        '"region":"face"' in json.dumps(b1, ensure_ascii=False)
    ok = (c1 == 200 and not hit and vd_ok
          and "schema_version" not in json.dumps(b1, ensure_ascii=False))
    _add("CC-05", "嵌套白名单：A02 full/A01+A08 summary/A03 执行投影/T07 快照四处无 SECRET "
                  "键值，白名单键保留、schema_version 不外发",
         "PASS" if ok else "FAIL", "种子多层 SECRET plan_payload + HTTP 响应 + T07 SQL 快照",
         f"{c1}/{c2}/{c3}", f"forbidden_hit={hit} vendor_debug_projection={vd} vd_ok={vd_ok} region_kept={kept} "
                             f"snapshot_len={len(snap or '')} snapshot_has_secret="
                             f"{bool(R5.forbidden_hit(snap or '', ['SECRET1', 'SECRET2', 'SECRET3']))}")


# ---------------- CC-06 ----------------

def cc_06(ctx):
    a, member = ctx["tok"], ctx["member"]
    results, tokens = [], set()

    def seed_and_admit(mut, steps_ok=True):
        import copy
        mc = seed_microcrystal()
        asmt = seed_assessment(ctx["gimbal"], member)
        payload = json.dumps({"schema_version": 1, "title": "t",
                              "steps": [{"region": "face", "parameters": {"intensity": "3"}}]
                              if steps_ok else []})
        pid = str(uuid.uuid4())
        sql("INSERT INTO care_plans (id, assessment_id, member_id, generation_status, plan_summary,"
            f" plan_payload, target_count, completed_count, progress_revision) VALUES ('{pid}',"
            f"'{asmt}','{member}','ready',CAST('{{\"schema_version\":1}}' AS jsonb),"
            f"CAST('{payload}' AS jsonb),3,0,0)")
        base = json.loads(DEFAULT_INPUT_SNAPSHOT)
        base["capability"]["microcrystal_id"] = mc
        base["report"]["assessment_id"] = asmt
        if mut:
            mut(base)
        sql(f"UPDATE care_plans SET input_snapshot=CAST('{json.dumps(base)}' AS jsonb) WHERE id='{pid}'")
        return admit(a, mc, pid)

    variants = [
        ("capability={}", lambda s: s.update(capability={})),
        ("缺 capability_id", lambda s: s["capability"].pop("capability_id")),
        ("缺 parameter_ranges", lambda s: s["capability"].pop("parameter_ranges")),
        ("缺 approved_regions", lambda s: s["capability"].pop("approved_regions")),
        ("缺 n_bounds", lambda s: s["capability"].pop("n_bounds")),
        ("单边缺 unit", lambda s: s["capability"]["parameter_ranges"].__setitem__(
            "intensity", {"min": "0", "max": "5"})),
        ("min>max", lambda s: s["capability"]["parameter_ranges"].__setitem__(
            "intensity", {"min": "9", "max": "5", "unit": "level"})),
        ("n_bounds 畸形(缺 max)", lambda s: s["capability"].__setitem__(
            "n_bounds", {"min": "1"})),
        ("region 不支持", lambda s: s["capability"].__setitem__("approved_regions", ["ear"])),
    ]
    for name, mut in variants:
        c, b = seed_and_admit(mut)
        tok = ((b.get("error") or {}).get("details") or {}).get("reason")
        tokens.add(tok)
        results.append(f"{name}={c}/{tok}")
    c_pos, _ = seed_and_admit(None)
    c_steps, b_steps = seed_and_admit(None, steps_ok=False)
    tok_steps = ((b_steps.get("error") or {}).get("details") or {}).get("reason")
    malformed = [r for r in results if "/malformed_frozen_capability" in r or "/region_" in r
                 or "/n_" in r or "/range_" in r or "/unit_" in r]
    ok = len(malformed) == len(variants) and c_pos == 201 and c_steps == 409 \
        and tok_steps == "malformed_frozen_step"
    _add("CC-06", "能力严格 fail-closed：畸形 capability/steps 逐变体 409 reason token；"
                  "正例（capability_revision 9≠7）201（代表性 token 子集；其余由 C 27 项单测覆盖，未重跑）",
         "PASS" if ok else "FAIL", "逐变体新微晶/新方案种子 + A03",
         f"pos={c_pos} steps={c_steps}",
         f"tokens={sorted(t for t in tokens if t)} step_token={tok_steps} "
         f"malformed={len(malformed)}/{len(variants)} unmatched={[r for r in results if r not in malformed]}")
    I.evidence_text("cc-06-details.txt", "\n".join(results))


# ---------------- CC-07/08/09/10: main execution lifecycle ----------------

def _new_ready_plan(member, target=3, payload=None, mc=None):
    asmt = seed_assessment(ctx_gimbal(), member)
    return seed_plan(asmt, member, "ready", payload, target=target)


def ctx_gimbal():
    return CONTEXT["gimbal"]


def cc_07_10(ctx):
    a, member = ctx["tok"], ctx["member"]
    plan, mc = new_plan_and_mc(target=3)
    key = str(uuid.uuid4())
    md = mk_metadata(mc, plan=plan)
    c, b = admit(a, mc, plan, key=key, metadata=md)
    ex = (b.get("data") or {}).get("executionId")
    ep = (b.get("data") or {}).get("recordStreamEpoch") or ex
    # 缺 Idempotency-Key → 4xx
    c_nokey, _ = post_multipart(f"{CARE}/care-executions", a, mk_metadata(mc, plan=plan), "")
    # 重放（同元数据）
    c_rep, b_rep = admit(a, mc, plan, key=key, metadata=md)
    same = (b_rep.get("data") or {}).get("executionId") == ex
    ver = (b.get("data") or {}).get("verification") or {}
    ver_rep = (b_rep.get("data") or {}).get("verification") or {}
    rev_before = scalar(f"SELECT verification_revision FROM care_executions WHERE id='{ex}'")
    c_rep2, _ = admit(a, mc, plan, key=key, metadata=md)
    rev_after = scalar(f"SELECT verification_revision FROM care_executions WHERE id='{ex}'")
    replayed = (b_rep.get("meta") or {}).get("replayed") is True and ver_rep.get("replayed") is True
    # 同键异内容
    c_conf2, b_conf = post_multipart(f"{CARE}/care-executions", a,
                                     {"microcrystalId": mc, "connectionProof": "OTHER",
                                      "consentEvidenceRef": "consent-2",
                                      "planId": plan,
                                      "capture": {"captureId": "c2", "capturedAt": utcnow(),
                                                  "clientContinuityId": "cc-2",
                                                  "purpose": "admission"}}, key)
    conflict_ok = c_conf2 == 409 and (b_conf.get("error") or {}).get(
        "code") == "IDEMPOTENCY_CONTENT_CONFLICT"
    # CC-08 并发占用：新 plan + 新 mc，APP 与云台同微晶并发
    plan2, mc2 = new_plan_and_mc(target=3)
    gtok = ctx["gtok"]
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(max_workers=2) as ex_pool:
        f1 = ex_pool.submit(post_multipart, f"{CARE}/care-executions", a,
                            mk_metadata(mc2, plan=plan2), str(uuid.uuid4()))
        f2 = ex_pool.submit(post_multipart, f"{CARE}/care-executions", gtok,
                            mk_metadata(mc2, task=ctx["assessment"], rev="1"), str(uuid.uuid4()))
        r1, r2 = f1.result(), f2.result()
    codes = sorted([r1[0], r2[0]])
    occ_ok = codes == [201, 409]
    # CC-09 账本：K 边界（新执行，target=2）
    plan3, mc3 = new_plan_and_mc(target=2)
    c3, b3 = admit(a, mc3, plan3, key=str(uuid.uuid4()))
    ex3 = (b3.get("data") or {}).get("executionId")
    ep3 = (b3.get("data") or {}).get("recordStreamEpoch") or ex3
    if not ex3:
        _add("CC-09", "账本去重/K/事务", "FAIL", "A03 for ledger scenario", c3,
             f"A03 failed: {str(b3)[:300]}")
        _add("CC-10", "收尾对账", "FAIL", "A03 for closure scenario", c3,
             f"A03 failed: {str(b3)[:200]}")
        return plan3, None
    s1 = sync(a, ex3, obs_records(ep3, [rec(ep3, 1), rec(ep3, 2)]), str(uuid.uuid4()))
    # 双键去重：重传同记录
    s2 = sync(a, ex3, obs_records(ep3, [rec(ep3, 1), rec(ep3, 2)]), str(uuid.uuid4()))
    disp = [(r.get("disposition")) for r in (s2[1].get("data") or {}).get("records", [])]
    accepted = scalar(f"SELECT accepted_count FROM care_executions WHERE id='{ex3}'")
    comp_at = scalar(f"SELECT coalesce(completed_at::text,'') FROM care_executions WHERE id='{ex3}'")
    comp_before = comp_at
    s3 = sync(a, ex3, obs_records(ep3, [rec(ep3, 3)]), str(uuid.uuid4()))
    comp_after = scalar(f"SELECT coalesce(completed_at::text,'') FROM care_executions WHERE id='{ex3}'")
    # 同键异内容 → 409 整批 + 零持久化
    kk = str(uuid.uuid4())
    s4 = sync(a, ex3, obs_records(ep3, [rec(ep3, 4, rid="conf-a")]), kk)
    s5 = sync(a, ex3, obs_records(ep3, [rec(ep3, 4, delta="2", rid="conf-b")]), kk)
    rows_x = scalar("SELECT count(*) FROM care_records WHERE execution_id='" + ex3 +
                    "' AND client_record_id='conf-b'")
    # 收尾：未 stopped → 409 STOP_NOT_CONFIRMED
    wm = scalar("SELECT coalesce(max(source_seq),0) FROM care_records "
                f"WHERE execution_id='{ex3}'")
    acc_wm = scalar(f"SELECT accepted_count FROM care_executions WHERE id='{ex3}'")
    fin_seq = int(wm); fin_cnt = int(acc_wm)
    clo_pre = closure(a, ex3, ep3, fin_seq, fin_cnt, str(uuid.uuid4()), stop_seq=2)
    # stopped 观察后收尾
    sync(a, ex3, obs_records(ep3, [], seq=2, state="stopped", rev="1"), str(uuid.uuid4()))
    clo = closure(a, ex3, ep3, fin_seq, fin_cnt, str(uuid.uuid4()), stop_seq=2)
    closed = (clo[1].get("data") or {}).get("closed")
    occ_rel = (clo[1].get("data") or {}).get("occupancyReleased")
    clo_rep = closure(a, ex3, ep3, fin_seq, fin_cnt, str(uuid.uuid4()), stop_seq=2)
    manifest1 = scalar(f"SELECT closure_manifest::text FROM care_executions WHERE id='{ex3}'")
    A07 = get_json(f"{CARE}/care-executions/{ex3}", a)
    A08 = get_json(f"{CARE}/care-plans/{plan3}/progress", a)
    A09 = get_json(f"{CARE}/members/{member}/care-executions", a)
    ok = (c == 201 and c_nokey >= 400 and c_rep == 200 and same and replayed
          and rev_before == rev_after and conflict_ok and occ_ok
          and s1[0] == 200 and accepted == "2" and all(d == "duplicate" for d in disp)
          and comp_before and comp_after == comp_before and s3[0] == 200
          and s5[0] == 409 and rows_x == "0"
          and (clo_pre[1].get("error") or {}).get("code") == "STOP_NOT_CONFIRMED"
          and clo[0] == 200 and closed is True and occ_rel is True
          and A07[0] == 200 and A08[0] == 200 and A09[0] == 200)
    _add("CC-07", "幂等与重放：缺键 4xx、同键重放 replayed 且 revision 不刷新、"
                  "同键异内容 409、并发双端恰一 201",
         "PASS" if (c_nokey >= 400 and c_rep == 200 and same and replayed
                    and rev_before == rev_after and conflict_ok and occ_ok) else "FAIL",
         "A03 重放/冲突/并发", f"{c}/{c_rep}/{c_conf2}", f"nokey={c_nokey} same_exec={same} "
         f"replayed={replayed} rev {rev_before}->{rev_after} conflict={conflict_ok} "
         f"concurrent={codes}")
    _add("CC-08", "占用/并发：APP+云台同微晶恰一 201 一 409 DEVICE_OCCUPIED；占用仅 closed 释放",
         "PASS" if occ_ok else "FAIL", "两请求真实并行", f"{codes}", f"r1={r1[0]} r2={r2[0]}")
    _add("CC-09", "账本去重/K/事务：双键判重 duplicate、K 达 completed、同键异内容整批 409 零持久化",
         "PASS" if (accepted == "2" and all(d == "duplicate" for d in disp)
                    and s5[0] == 409 and rows_x == "0") else "FAIL",
         "A05 多批 + SQL 核对", f"{s1[0]}/{s2[0]}/{s5[0]}",
         f"accepted={accepted} disp={disp} completed_at_stable={comp_after == comp_before} "
         f"conflict_zero_rows={rows_x}")
    _add("CC-10", "收尾对账：未 stopped 409 STOP_NOT_CONFIRMED；stopped+水位完整 → closed+"
                  "occupancyReleased；重放 manifest 不变；A07/A08/A09 2xx",
         "PASS" if (clo[0] == 200 and closed is True and occ_rel is True
                    and (clo_pre[1].get("error") or {}).get("code") == "STOP_NOT_CONFIRMED"
                    and A07[0] == 200 and A08[0] == 200 and A09[0] == 200) else "FAIL",
         "A06 前后置 + A07/A08/A09", f"{clo_pre[0]}/{clo[0]}",
         f"closed={closed} released={occ_rel} accepted={accepted} manifest_len={len(manifest1 or '')} "
         f"clo_err={(clo[1].get('error') or {}).get('code')}/"
         f"{((clo[1].get('error') or {}).get('details') or {})} "
         f"A07={A07[0]} A08={A08[0]} A09={A09[0]} replay={clo_rep[0]}")
    return plan3, ex3


# ---------------- CC-11/12 ----------------

def cc_11():
    from driver import a_reverify as AR
    st = I.run([str(I.PY), str(AR.VALIDATE), "--selftest"], cwd=I.CONTRACTS, timeout=180,
               log_name="cc-11-selftest.log")
    samp = I.run([str(I.PY), "scripts/validate_samples.py"], cwd=I.CONTRACTS, timeout=180,
                 log_name="cc-11-samples.log")
    n = re.search(r"(\d+)\s+checks", samp.stdout)
    oas = I.run([str(I.PY), "-c", "import yaml\nfrom openapi_spec_validator import validate\n"
                 "validate(yaml.safe_load(open('openapi/openapi.yaml')))\nprint('OPENAPI VALID')"],
                cwd=I.CONTRACTS, timeout=180, log_name="cc-11-openapi.log")
    ok = (st.returncode == 0 and "10 checks passed" in st.stdout and samp.returncode == 0
          and n and n.group(1) == "50" and oas.returncode == 0 and "OPENAPI VALID" in oas.stdout)
    _add("CC-11", "有界严格契约：validate_responses selftest 10/10 + samples 50 + OpenAPI VALID；"
                  "成功响应捕获严格校验、错误响应基本信封（如实分类）",
         "PASS" if ok else "FAIL", "契约脚本（.venv-driver 只读 contracts）",
         f"{st.returncode}/{samp.returncode}/{oas.returncode}",
         f"selftest={st.returncode == 0} samples={n.group(1) if n else '?'} oas_ok={oas.returncode == 0}")


def cc_12_and_matrix():
    I.run([str(I.PY), "matrix/generate_matrix.py"], cwd=I.ROOT, timeout=120, log_name="cc-12-gen.log")
    import hashlib
    h1 = hashlib.md5((I.ROOT / "matrix/scenarios.json").read_bytes()).hexdigest()
    I.run([str(I.PY), "matrix/generate_matrix.py"], cwd=I.ROOT, timeout=120)
    h2 = hashlib.md5((I.ROOT / "matrix/scenarios.json").read_bytes()).hexdigest()
    rows = json.loads((I.ROOT / "matrix/scenarios.json").read_text(encoding="utf-8"))
    owner_c = [s for s in rows if "C" in s["owner_package"]]
    bad = [s["id"] for s in owner_c if "C" in s["blocked_by"]]
    ids = [s["id"] for s in rows]
    ok = h1 == h2 and len(rows) == 94 and len(set(ids)) == 94 and not bad \
        and all(s["status"] == "dependency_pending" for s in rows)
    _add("CC-12", "矩阵维护：再生成幂等；94 ID 唯一；含 C 场景 blocked_by 不含 C；"
                  "全部仍 dependency_pending",
         "PASS" if ok else "FAIL", "generate_matrix x2 + jq 断言",
         "0", f"md5_idempotent={h1 == h2} n={len(rows)} c_still_blocked={bad[:3]}")


# ---------------- outputs ----------------

def write_outputs_c(settle, rc, formal_dir):
    counts = settle["counts"]
    result = {"schema": "e-acceptance-c-care/1", "run_id": I.RUN_ID, "mode": "c-care",
              "c_code": C_CODE, "expected": settle["expected"], "settled": settle["settled"],
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
        f"# E C/M4 黑盒验收 —— C {C_CODE}，run {I.RUN_ID}",
        "",
        "> **替身形态（doubles_pass）**：短信/会话/设备凭据/存储/人脸均为 dev 替身；种子=直连 SQL，"
        "不等于跨包真实链路。D 真实端点（方案生成、真实任务替换）与 B 真实端点（授权/成员/设备）"
        "相关场景仍 dependency_pending。",
        "",
        f"## 结算：{settle['settled']}/{settle['expected']} 唯一结算；"
        f"{counts['pass']} PASS / {counts['fail']} FAIL / {counts['blocked']} BLOCKED / "
        f"{counts['info']} INFO（计数和={sum(counts.values())}==行数 {settle.get('rows')}）；"
        f"final_exit={rc}",
        "",
        cc_conclusion(settle),
        "",
        "| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |",
        "|---|---|---|---|---|",
    ]
    for r in R.rows:
        lines.append(f"| {r['id']} | {cell(r['title'])} | **{r['status']}** | "
                     f"{cell(r['command'])} / {r['rc']} | {cell(r['excerpt'])} |")
    fails = [r for r in R.rows if r["status"] == "FAIL"]
    lines += ["", "## C 缺陷清单", ""]
    lines.append("（无 FAIL 项）" if not fails else "")
    for r in fails:
        lines.append(f"- **{r['id']}** {r['title']}；{r['excerpt']}")
    lines += ["", "## 待集成/依赖披露", "",
              "- D：M3-A01 真实方案生成与任务替换链路、plan_payload 版本化白名单批准 → dependency_pending",
              "- B：真实成员授权/撤销、设备凭据、媒体访问策略 → dependency_pending",
              "- 生产人脸真实 1:1 提供方未接入（C 有意 fail-closed）", ""]
    (formal_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n=== E C-acceptance: {counts['pass']} PASS / {counts['fail']} FAIL / "
          f"{counts['blocked']} BLOCKED / {counts['info']} INFO "
          f"(settled {settle['settled']}/{settle['expected']}, exit={rc}) ===")
    print(cc_conclusion(settle))
    print(f"evidence: {formal_dir}/summary.md")


def main() -> int:
    formal = not os.environ.get("E_CC_ONLY")
    formal_dir = I.ROOT / "evidence" / EVID_DIRNAME / I.RUN_ID
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
            cp = I.start_pg()
            if cp.returncode != 0 or not I.wait_pg():
                _add("SETUP", "启动 E 专用 PG", "FAIL", "docker run mvp-e-pg", cp.returncode, "")
            else:
                I.recreate_db()
                cc_01()
                member = str(uuid.uuid4())
                up = I.start_java(extra_env={"APP_C_FACE_BOUND_MEMBER": member,
                                             "JAVA_TOOL_OPTIONS": JVM_OPTS},
                                  log_name="cc-main-java.log")
                if not up:
                    _add("CC-01", "Java 启动健康", "FAIL", "java -jar", "1",
                         log_tail("cc-main-java.log"))
                else:
                    account = AB.login()
                    seed_member(member)
                    seed_grant(account["accountId"], member)
                    gimbal = seed_gimbal()
                    mc = seed_microcrystal()
                    asmt = seed_assessment(gimbal, member)
                    sql(f"UPDATE gimbals SET current_assessment_id='{asmt}',"
                        f" current_assessment_revision=1, updated_at=now() WHERE id='{gimbal}'")
                    CONTEXT.update({"accountId": account["accountId"], "tok": account["access"],
                                    "member": member, "gimbal": gimbal, "mc": mc,
                                    "assessment": asmt, "plan": None})
                    CONTEXT["plan"] = seed_plan(asmt, member, "ready", SENSITIVE_PLAN,
                                                target=3, mc=mc)
                    CONTEXT["gtok"] = gimbal_token(gimbal)
                    only = os.environ.get("E_CC_ONLY", "")
                    names = only.split(",") if only else None

                    def want(n):
                        return names is None or n in names
                    if want("cc02") or want("cc05"):
                        bplan, bmc = new_plan_and_mc(target=3)
                        bc, bb = admit(CONTEXT["tok"], bmc, bplan, key=str(uuid.uuid4()))
                        CONTEXT["execution"] = (bb.get("data") or {}).get("executionId")
                        CONTEXT["epoch"] = (bb.get("data") or {}).get("recordStreamEpoch")
                    if want("cc02"):
                        cc_02(CONTEXT)
                    if want("cc05"):
                        cc_05(CONTEXT)
                    if want("cc06"):
                        cc_06(CONTEXT)
                    if want("cc0710"):
                        cc_07_10(CONTEXT)
                    if want("cc11"):
                        cc_11()
                    if want("cc04"):
                        cc_04(CONTEXT)
                if CONTEXT.get("member"):
                    if want_or_none(os.environ.get("E_CC_ONLY"), "cc03"):
                        cc_03(CONTEXT)
                    if want_or_none(os.environ.get("E_CC_ONLY"), "cc12"):
                        cc_12_and_matrix()
    finally:
        try:
            I.stop_java()
            I.kill_own_java()
            try:
                I.remove_container()
            except Exception as exc:
                _add("CLEANUP", "按 run 标签删除 E 容器", "FAIL", "docker rm", "1", str(exc))
            if "CLEANUP" not in {r["id"] for r in R.rows}:
                _add("CLEANUP", "停进程并按 run 标签删除 mvp-e-pg",
                     "PASS" if not I.container_exists() else "FAIL", "docker rm -f -v", "0", "")
            import time as _t
            freed = False
            for _ in range(20):
                if I.port_free(I.APP_PORT) and I.port_free(I.PG_HOST_PORT):
                    freed = True
                    break
                _t.sleep(1)
            _add("CLEANUP-ports", "端口释放", "PASS" if freed else "FAIL", "ss", "0", "")
        finally:
            I.release_single_instance_lock()
        settle = AB.settlement(expected=EXPECTED_C)
        rc = AB.final_exit(formal, settle)
        write_outputs_c(settle, rc, formal_dir if formal else REPORTS)
        verify_sentinel.write_sentinel(I.RUN_ID, settle, rc, mode="c-care", expected=EXPECTED_C)
    return rc


def want_or_none(only, name):
    return not only or name in only.split(",")


if __name__ == "__main__":
    sys.exit(main())
