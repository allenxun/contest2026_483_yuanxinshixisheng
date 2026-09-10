#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E 对 A 候选基线的独立基础验收：AB-01..AB-11 + N1..N3。

正式模式（无 E_AB_ONLY）必须逐项唯一结算 EXPECTED_CHECKS；缺项/多项 → exit 4。
诊断模式（E_AB_ONLY=...）：只写 reports/，标注 PARTIAL，绝不写/覆盖 evidence/ 正式路径。
真实 PG/Java/Worker；dev/test 替身 → doubles_pass，不宣称真实供应商接入。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from driver import infra as I  # noqa: E402
from driver.infra import R, REPORTS, PG_DB, APP_BASE  # noqa: E402

BASELINE = json.loads((I.ROOT / "config" / "baseline.json").read_text(encoding="utf-8"))["a_baseline"]

# 正式模式必须结算的检查 ID 全集（诊断模式允许子集）。
EXPECTED_CHECKS = frozenset({
    "SETUP-pg",
    "AB-01a", "AB-01b", "AB-01c",
    "AB-02a", "AB-02b", "AB-02c", "AB-02d",
    "AB-03",
    "AB-04a", "AB-04b", "AB-04c", "AB-04d", "AB-04e", "AB-04f", "AB-04g", "AB-04h", "AB-04i",
    "AB-05a", "AB-05b", "AB-05c", "AB-05d", "AB-05e", "AB-05f", "AB-05g", "AB-05h",
    "AB-06a", "AB-06b", "AB-06c", "AB-06d",
    "AB-07a", "AB-08a", "AB-08b",
    "AB-09a/N1j", "AB-09b", "AB-09c", "AB-09d",
    "AB-10a", "AB-10b", "AB-10c",
    "AB-11a", "AB-11b", "AB-11c",
    "N1-db", "N1-py-schema", "N1-py-runtime",
    "N2-db", "N2-codereview", "N2-http",
    "N3-media",
    "CLEANUP", "CLEANUP-ports",
})

CTX: dict[str, str] = {}
LOGIN_DEBUG = {"step": "", "code": "", "body": ""}


# ------------------------------------------------------------------ helpers

def _excerpt_cp(cp, n=300):
    return (((cp.stdout or "") + (cp.stderr or "")).strip().replace("\n", " "))[:n]


def add(cid, title, status, command="", rc="", excerpt="", doubles="doubles_pass", blocked=""):
    if blocked:
        excerpt = blocked
    R.add(cid, title, status, command, rc, excerpt, doubles)


# ------------------------------------------------------------------ AB-10 / N3 fail-closed

PROD_VARIANTS = [
    # prod 提供 app.env=production；额外激活 dev 让替身 bean 存在，ProductionFailClosedValidator
    # 才能在 afterSingletonsInstantiated 运行并输出逐项原因行（纯 prod 无 provider 会在 bean
    # 装配阶段就失败，观察不到 media 行——那属于“缺真实提供方”的接线失败）。
    ("AB-10a", "prod+doubles",
     {"SPRING_PROFILES_ACTIVE": "prod,dev", "APP_PROVIDERS_MODE": "doubles"},
     "SessionProvider=doubles/disabled only"),
    ("AB-10b", "prod+owner-dev",
     {"SPRING_PROFILES_ACTIVE": "prod,dev", "APP_PROVIDERS_MODE": "doubles",
      "APP_MEDIA_ACCESS_MODE": "owner-dev"},
     "app.media.access-mode=owner-dev"),
    ("AB-10c", "prod+allow-any",
     {"SPRING_PROFILES_ACTIVE": "prod,dev", "APP_PROVIDERS_MODE": "doubles",
      "APP_MEDIA_ALLOW_ANY_AUTHENTICATED": "true"},
     "app.media.allow-any-authenticated=true"),
]


def stage_ab10_failclosed():
    """黑盒启动拒绝：production 三种变体分别断言具体拒绝原因行。"""
    for cid, name, extra, expect_line in PROD_VARIANTS:
        log = f"java-prod-{name.replace('+', '_')}.log"
        I.start_java(extra_env=extra, log_name=log, wait=False)
        proc = I.JAVA_PROC
        try:
            rc = proc.wait(timeout=90) if proc else "no-proc"
        except Exception:
            rc = "timeout(still running)"
            if proc:
                proc.kill()
        exited = not I.java_alive()
        text = (REPORTS / log).read_text(encoding="utf-8", errors="replace")
        line_ok = expect_line in text
        I.stop_java()
        add(cid, f"fail-closed black-box：{name} 启动被拒且日志含具体原因行",
            "PASS" if exited and rc != 0 and line_ok else "FAIL",
            f"java -jar (SPRING_PROFILES_ACTIVE=prod, {name})", rc,
            f"exited={exited} reason_line={line_ok} : {expect_line}")


# ------------------------------------------------------------------ build + language

def stage_build_and_language():
    cp = I.run(["mvn", "-B", "-q", "-DskipTests", "package"], cwd=I.JAVA_DIR, timeout=1800,
               log_name="mvn-package.log")
    jar_ok = any((I.JAVA_DIR / "target").glob("web-java-*.jar")) if cp.returncode == 0 else False
    add("AB-01a", "Java 构建（-DskipTests package）产出可运行 jar",
        "PASS" if cp.returncode == 0 and jar_ok else "FAIL",
        "mvn -B -q -DskipTests package", cp.returncode, _excerpt_cp(cp))
    cp2 = I.run(["mvn", "-B", "-q", "test",
                 "-Dtest=SchemaVersionBoundaryTest,ProductionFailClosedTest"],
                cwd=I.JAVA_DIR, timeout=1200, log_name="mvn-targeted-tests.log")
    add("AB-09a/N1j", "Java 目标测试（真实类）：SchemaVersionBoundaryTest（N1 服务层整数校验）"
                      " + ProductionFailClosedTest（N3 fail-closed，targeted）",
        "PASS" if cp2.returncode == 0 else "FAIL",
        "mvn -B -q test -Dtest=SchemaVersionBoundaryTest,ProductionFailClosedTest",
        cp2.returncode, _excerpt_cp(cp2))
    for cid, title, cmd in [
        ("AB-09b", "jcs.py selftest（17 向量权威数对）", [str(I.PY), "scripts/jcs.py", "selftest"]),
        ("AB-09c", "validate_samples.py（样例+向量重算）",
         [str(I.PY), "scripts/validate_samples.py"]),
    ]:
        cp3 = I.run(cmd, cwd=I.CONTRACTS, timeout=300,
                    log_name=title.split("（")[0].strip().replace(" ", "_") + ".log")
        add(cid, title, "PASS" if cp3.returncode == 0 else "FAIL", " ".join(cmd[1:]),
            cp3.returncode, ((cp3.stdout or "").strip().splitlines() or [""])[-1][:200])
    code = ("import yaml\nfrom openapi_spec_validator import validate\n"
            "validate(yaml.safe_load(open('openapi/openapi.yaml')))\nprint('OPENAPI VALID')")
    cp4 = I.run([str(I.PY), "-c", code], cwd=I.CONTRACTS, timeout=300,
                log_name="openapi-validate.log")
    add("AB-09d", "openapi_spec_validator（基础契约）",
        "PASS" if cp4.returncode == 0 and "OPENAPI VALID" in cp4.stdout else "FAIL",
        "python -c validate(openapi.yaml)", cp4.returncode, _excerpt_cp(cp4))


# ------------------------------------------------------------------ AB-01/03

def stage_ab01_restart_and_ab03():
    ok1 = I.start_java(log_name="java-app-1.log")
    pid1 = I.JAVA_PROC.pid if I.JAVA_PROC else "-"
    add("AB-01b", "Java dev 启动 + /actuator/health UP（健康绑定子进程存活）",
        "PASS" if ok1 else "FAIL", f"java -jar (SERVER_PORT={I.APP_PORT}, db={PG_DB})",
        "0" if ok1 else "1", f"first pid={pid1}")
    if not ok1:
        return False
    I.stop_java()
    ok2 = I.start_java(log_name="java-app-2.log")
    log2 = (REPORTS / "java-app-2.log").read_text(encoding="utf-8", errors="replace")
    noop = "No migration necessary" in log2
    add("AB-01c", "SIGTERM 停止 → 再启动 UP；Flyway no-op（重复启动无破坏）",
        "PASS" if ok2 and noop else "FAIL", "restart cycle", "0" if ok2 else "1",
        f"second UP={ok2}; flyway_noop={noop}")
    tables = I.sql_scalar("SELECT count(*) FROM information_schema.tables "
                          "WHERE table_schema='public' AND table_type='BASE TABLE'")
    hist = I.sql_scalar("SELECT string_agg(version, ',') FROM "
                        "(SELECT version FROM flyway_schema_history ORDER BY installed_rank) t")
    hist_ok = I.sql_scalar("SELECT count(*) FROM flyway_schema_history WHERE success")
    expected = {"idempotency_requests", "accounts", "members", "member_access_grants", "gimbals",
                "microcrystals", "skin_assessments", "care_plans", "care_executions",
                "care_records", "notification_destinations", "notifications", "media_objects",
                "async_jobs"}
    got = set(I.sql_scalar("SELECT string_agg(table_name, ',') FROM information_schema.tables "
                           "WHERE table_schema='public' AND table_type='BASE TABLE' "
                           "AND table_name <> 'flyway_schema_history'").split(","))
    ok3 = got == expected and hist.startswith("1") and "2" in hist
    add("AB-03", f"全新 E 库 Flyway V1+V2 迁移：14 表（实际 {len(got)}），版本={hist}",
        "PASS" if ok3 else "FAIL", "fresh db migrate via app start", tables,
        f"missing={sorted(expected - got)} extra={sorted(got - expected)} "
        f"history={hist} success_rows={hist_ok}")
    return ok2


# ------------------------------------------------------------------ AB-02

def stage_ab02_worker():
    cp = I.worker_cli("--check", timeout=120)
    add("AB-02a", "worker --check 连通自检（E 库）", "PASS" if cp.returncode == 0 else "FAIL",
        "python -m mvp_worker --check", cp.returncode, _excerpt_cp(cp))
    proc = I.start_worker()
    ready, why = I.wait_worker_ready(timeout_s=45)
    add("AB-02b", "worker 运行循环 + /healthz /readyz UP（健康绑定本 run 子进程存活）",
        "PASS" if ready else "FAIL", "python -m mvp_worker (loop)",
        "0" if ready else (proc.returncode if proc.poll() is not None else "timeout"), why)
    rc, graceful = I.terminate_worker(timeout_s=40)
    add("AB-02c", "SIGTERM 优雅停机：真实 Popen wait 后 returncode==0 且日志见停机行",
        "PASS" if rc == 0 and graceful else "FAIL",
        "proc.send_signal(SIGTERM) → proc.wait()", rc,
        f"graceful_log={graceful}（未依赖已清空变量）")


WORKER_TEST_FILES = ["tests/test_claim.py", "tests/test_renew.py", "tests/test_expire.py",
                     "tests/test_complete.py", "tests/test_attempt_ceiling.py",
                     "tests/test_unsupported.py"]


def stage_ab02d_targeted_pytest():
    """E 定向执行与基础/恢复/版本校验直接相关的 worker pytest（E 专属 PG，不跑全量）。"""
    env = {
        "MVP_A_PG_CONTAINER": I.PG_CONTAINER,
        "MVP_A_PG_HOST_PORT": str(I.PG_HOST_PORT),
        "MVP_A_PG_USER": I.PG_USER,
        "MVP_A_PG_PASSWORD": I.PG_PASSWORD,
        "MVP_A_PG_DSN": f"postgresql://{I.PG_USER}:{I.PG_PASSWORD}@127.0.0.1:{I.PG_HOST_PORT}/postgres",
        "PYTHONPATH": str(I.WORKER_DIR / "src"),
    }
    cmd = [str(I.PY), "-m", "pytest", "-q", *WORKER_TEST_FILES]
    cp = I.run(cmd, cwd=I.WORKER_DIR, env=env, timeout=1200, log_name="ab02d-worker-pytest.log")
    out = (cp.stdout or "") + (cp.stderr or "")
    passed = ""
    for tok in out.split():
        if tok.isdigit() and "passed" in out:
            passed = tok
            break
    add("AB-02d", "E 定向执行 worker pytest（claim/renew/expire/complete/attempt-ceiling/"
                  "unsupported；E 专属 PG 临时库，绝不混 A 库）",
        "PASS" if cp.returncode == 0 and "passed" in out else "FAIL",
        "pytest -q " + " ".join(WORKER_TEST_FILES), cp.returncode,
        f"passed={passed} : {' '.join(out.strip().splitlines()[-1:])[:200]}")


# ------------------------------------------------------------------ N1 db

def stage_n1_sql_boundary():
    variants = [
        ("array", "[\"schema_version\"]", False),
        ("null_version", '{"schema_version":null}', False),
        ("string_version", '{"schema_version":"1"}', False),
        ("bool_version", '{"schema_version":true}', False),
        ("missing_key", '{}', False),
        ("int1", '{"schema_version":1}', True),
        ("fractional", '{"schema_version":1.5}', True),
        ("negative", '{"schema_version":-2}', True),
    ]
    detail, ok = [], True
    for name, payload, should_accept in variants:
        cp = I.psql("INSERT INTO async_jobs (job_type,dedup_key,owner_type,owner_id,payload) VALUES "
                    f"('system.echo','e-n1-{name}-{I.SUFFIX}','system',gen_random_uuid(),'{payload}')")
        accepted = cp.returncode == 0
        ok = ok and accepted == should_accept
        detail.append(f"{name}:{'accept' if accepted else 'rej'}")
    add("N1-db", "JSONB 写入边界（DB object+number CHECK）：非对象/null/字符串/bool/缺键拒绝，"
                 "整数接受；小数/负数 DB 放行=已知限制（服务层兜底）",
        "PASS" if ok else "FAIL", "psql INSERT async_jobs.payload 变体", "0/1", " ".join(detail))


# ------------------------------------------------------------------ AB-04

ARRAY_SEED = None  # (种子 SQL 常量见下)


def stage_ab04_constraints():
    seed = open(I.ROOT / "driver" / "seed_ab04.sql", encoding="utf-8").read()
    cp = I.psql(seed)
    add("AB-04a", "约束负例最小父链种子", "PASS" if cp.returncode == 0 else "FAIL",
        "psql seed", cp.returncode, _excerpt_cp(cp))
    negs = [
        ("AB-04b", "同一微晶第二个未收尾执行 → 拒绝（双占用）", "uq_execution_open_microcrystal",
         "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id, controller_type, controller_account_id, controller_installation_id, assessment_id_at_start, source_request_id) VALUES ('77777777-7777-4777-8777-777777777702','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601','app','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','inst-seed-owner-2','44444444-4444-4444-8444-444444444401','11111111-1111-4111-8111-111111111103')"),
        ("AB-04c", "同一执行重复源三元组记录 → 拒绝（双记录）", "uq_record_source",
         "INSERT INTO care_records (id, execution_id, client_record_id, plan_id, member_id, microcrystal_id, count_delta, source_epoch, source_seq, payload_hash, payload) VALUES ('99999999-9999-4999-8999-999999999902','77777777-7777-4777-8777-777777777701','rec-b','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601',1,'epoch-1',1,'a0000000000000000000000000000000000000000000000000000000000000002','{\"schema_version\":1}')"),
        ("AB-04d", "app 控制端缺 account/installation → 控制端归属 CHECK 拒绝",
         "ck_execution_controller_ownership",
         "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id, controller_type, assessment_id_at_start, source_request_id) VALUES ('77777777-7777-4777-8777-777777777703','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601','app','44444444-4444-4444-8444-444444444401','11111111-1111-4111-8111-111111111104')"),
        ("AB-04e", "active 通知目标无 registration → CHECK 拒绝", "ck_destination_active_fields",
         "INSERT INTO notification_destinations (id, installation_id, account_id, status, session_ref) VALUES ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb8','inst-b8','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','active','sess-b8')"),
        ("AB-04f", "T13 (principal,operation,key) 重复 → 拒绝", "uq_idem_principal",
         "INSERT INTO idempotency_requests (principal_type, principal_id, operation, idempotency_key, payload_hash) VALUES ('app_account','accept-seed','seed.op','k-asm-1','b0000000000000000000000000000000000000000000000000000000000000000')"),
        ("AB-04g", "members (identity_namespace,face_subject_ref) 双非空重复 → 拒绝",
         "uq_members_identity",
         "INSERT INTO members (identity_namespace, face_subject_ref) VALUES ('accept-ns','face-seed-1')"),
        ("AB-04h", "skin_assessments 非法 status → CHECK 拒绝", "ck_assessment_status",
         "INSERT INTO skin_assessments (gimbal_id, member_id, status, source_request_id) VALUES ('33333333-3333-4333-8333-333333333301','22222222-2222-4222-8222-222222222201','bogus','11111111-1111-4111-8111-111111111105')"),
        ("AB-04i", "skin_assessments current_photo_version=0 → CHECK 拒绝",
         "ck_assessment_current_photo_version",
         "INSERT INTO skin_assessments (gimbal_id, member_id, current_photo_version, source_request_id) VALUES ('33333333-3333-4333-8333-333333333301','22222222-2222-4222-8222-222222222201',0,'11111111-1111-4111-8111-111111111106')"),
    ]
    for cid, title, constraint, sql in negs:
        cp = I.psql(sql)
        ok = cp.returncode != 0 and constraint in cp.stderr
        add(cid, f"{title}（拒因含 {constraint}）", "PASS" if ok else "FAIL",
            "psql negative INSERT", cp.returncode, f"constraint_seen={constraint in cp.stderr}")


# ------------------------------------------------------------------ AB-05

def login(identity_tag=None):
    """建立 APP 会话。identity_tag 可指定独立身份（不同 phone/installationId）；
    缺省沿用 I.SUFFIX（既有行为不变）。"""
    tag = identity_tag or I.SUFFIX
    try:
        digits = f"{int(tag, 16) % 100000000:08d}"
    except ValueError:
        digits = ("".join(ch for ch in tag if ch.isdigit()) or "0").rjust(8, "0")[-8:]
    phone = f"+86138{digits}"
    installation = f"e-inst-{tag}"
    code, body, _ = I.http("POST", "/api/v1/auth/sms-challenges",
                           body={"phone": phone, "purpose": "login"})
    if code != 200:
        LOGIN_DEBUG.update(step="sms-challenges", code=str(code), body=json.dumps(body)[:200])
        return None
    chal = body["data"]["challengeId"]
    code, body, _ = I.http("POST", "/api/v1/auth/sessions",
                           body={"challengeId": chal, "code": "123456",
                                 "installationId": installation})
    if code != 200:
        LOGIN_DEBUG.update(step="sessions", code=str(code), body=json.dumps(body)[:200])
        return None
    d = body["data"]
    return {"phone": phone, "accountId": d["accountId"], "installationId": installation,
            "access": d["accessToken"], "refresh": d["refreshToken"]}


def _affected_rows(update_sql: str) -> tuple[bool, int]:
    """用 CTE 包装 UPDATE ... RETURNING 精确取影响行数（避免 psql 命令标签干扰）。"""
    cp = I.psql(f"WITH u AS ({update_sql}) SELECT count(*) FROM u")
    if cp.returncode != 0:
        return False, -1
    try:
        return True, int(cp.stdout.strip())
    except ValueError:
        return False, -1


def _valid_token(sess) -> int:
    """已认证业务 stub → 501 视为会话有效（非 401）。"""
    code, _, _ = I.http("GET", "/api/v1/me/member-access-grants", token=sess["access"])
    return code


def stage_ab05_auth():
    code, body, _ = I.http("GET", "/api/v1/me/member-access-grants")
    add("AB-05a", "无 token → 401 AUTH_REQUIRED 信封",
        "PASS" if code == 401 and body.get("error", {}).get("code") == "AUTH_REQUIRED" else "FAIL",
        "GET /me/member-access-grants", code, json.dumps(body)[:200])
    code, body, _ = I.http("GET", "/api/v1/me/member-access-grants", token="not-a-real-token")
    add("AB-05b", "伪造 Bearer → 401 SESSION_INVALID",
        "PASS" if code == 401 and body.get("error", {}).get("code") == "SESSION_INVALID" else "FAIL",
        "GET with forged token", code, json.dumps(body)[:200])
    s = login()
    if not s:
        add("AB-05c", "手机号会话建立（替身 123456）", "FAIL", "auth flow",
            LOGIN_DEBUG["code"], f"step={LOGIN_DEBUG['step']} {LOGIN_DEBUG['body']}")
        return None
    add("AB-05c", "手机号会话建立（SMS 替身 123456 + installationId）", "PASS",
        "POST sms-challenges→sessions", 200,
        f"accountId={s['accountId']} 前置有效码={_valid_token(s)}")

    # AB-05d：独立会话；轮换后旧 refresh 拒绝（旧 access 也已撤销，用独立会话隔离）
    sd = login()
    c_new, _, _ = I.http("POST", "/api/v1/auth/session-refreshes",
                         body={"refreshCredential": sd["refresh"],
                               "installationId": sd["installationId"]})
    c_reuse, b_reuse, _ = I.http("POST", "/api/v1/auth/session-refreshes",
                                 body={"refreshCredential": sd["refresh"],
                                       "installationId": sd["installationId"]})
    ok = c_new == 200 and c_reuse == 401 and \
        b_reuse.get("error", {}).get("code") == "SESSION_INVALID"
    add("AB-05d", "refresh 轮换后旧 refresh token → 401 SESSION_INVALID（独立会话）",
        "PASS" if ok else "FAIL", "POST session-refreshes (old reused)", f"{c_new}/{c_reuse}",
        json.dumps(b_reuse)[:200])

    # AB-05e：独立会话；真实 accountId；UPDATE 影响行数==1；变更前有效、变更后 401
    for cid, title, sql_fmt in [
        ("AB-05e", "账号 disabled 后旧 token → 401 SESSION_INVALID（每请求复核）",
         "UPDATE accounts SET status='disabled' WHERE id='{aid}' RETURNING id"),
        ("AB-05f", "auth_revision 递增后旧 token → 401（撤销代次不可复活）",
         "UPDATE accounts SET auth_revision=auth_revision+1 WHERE id='{aid}' RETURNING id"),
    ]:
        se = login()
        before = _valid_token(se)
        ok_rows, changed = _affected_rows(sql_fmt.format(aid=se["accountId"]))
        after = _valid_token(se)
        after_body = I.http("GET", "/api/v1/me/member-access-grants", token=se["access"])[1]
        ok = before == 501 and ok_rows and changed == 1 and after == 401 and \
            after_body.get("error", {}).get("code") == "SESSION_INVALID"
        I.psql(f"UPDATE accounts SET status='active' WHERE id='{se['accountId']}'")
        add(cid, title, "PASS" if ok else "FAIL", "独立会话 → 变更真实 accountId → GET",
            f"{before}->{after}", f"rows_changed={changed} account={se['accountId'][:8]}")

    # AB-05g：revision 变更后重新登录并验证新会话有效
    sg = login()
    add("AB-05g", "revision 变更后重新登录成功且新会话有效（非仅返回 200）",
        "PASS" if sg and _valid_token(sg) == 501 else "FAIL", "POST sessions again + GET",
        "200", f"new_session_valid={bool(sg) and _valid_token(sg) == 501}")

    # AB-05h：云台会话独立；轮换 credential_version（影响行数==1）；前后对比
    cred = f"E-GIM-{I.SUFFIX}"
    gid = str(uuid.uuid4())
    I.psql("INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version) VALUES "
           f"('{gid}','{cred}','{cred}',1)")
    code, body, _ = I.http("POST", "/api/v1/gimbal-sessions",
                           body={"credential": cred, "credentialVersion": "1", "proof": "proof-e"})
    gtok = body.get("data", {}).get("sessionToken") if code == 200 else None
    before = I.http("GET", "/api/v1/me/member-access-grants", token=gtok)[0] if gtok else "-"
    ok_rows, changed = _affected_rows(
        f"UPDATE gimbals SET credential_version=credential_version+1 WHERE id='{gid}' RETURNING id")
    code2, body2, _ = I.http("GET", "/api/v1/me/member-access-grants", token=gtok) if gtok \
        else ("-", {}, {})
    ok = code == 200 and before == 501 and ok_rows and changed == 1 and code2 == 401 and \
        body2.get("error", {}).get("code") == "SESSION_INVALID"
    add("AB-05h", "云台凭据轮换后旧云台 token → 401（独立云台会话，影响行数=1）",
        "PASS" if ok else "FAIL", "gimbal-sessions → rotate → old token GET",
        f"{code}/{before}->{code2}", f"rows_changed={changed}")
    return sg or s


# ------------------------------------------------------------------ AB-06 / AB-08 / AB-11

def request_id_ok(header_value, body) -> bool:
    """X-Request-Id 与 body.requestId 均须非空且相等（双缺失 None==None 不算通过）。"""
    hdr = (header_value or "").strip() if isinstance(header_value, str) else ""
    brid = (body or {}).get("requestId") if isinstance(body, dict) else None
    brid = brid.strip() if isinstance(brid, str) else ""
    return bool(hdr) and bool(brid) and hdr == brid


def stage_ab0608_echo(s):
    tok = s["access"]
    key = f"e-echo-{I.SUFFIX}"
    payload = {"message": "E 独立验收回声", "numbersAsStrings": ["42", "7"]}
    code, body, _ = I.http("POST", "/api/v1/system/echo-jobs", token=tok,
                           body=payload, headers={"Idempotency-Key": key})
    job = body.get("data", {}).get("jobId")
    ok = code == 200 and body.get("data", {}).get("status") == "queued" and job
    add("AB-06a", "echo POST → 200 queued + jobId", "PASS" if ok else "FAIL",
        "POST /system/echo-jobs (Idempotency-Key)", code, json.dumps(body)[:250])
    if not ok:
        return
    CTX["job"] = job
    code, body, _ = I.http("POST", "/api/v1/system/echo-jobs", token=tok, body=payload,
                           headers={"Idempotency-Key": key})
    add("AB-08a", "T13 同 Idempotency-Key 同内容重放 → 同 jobId + meta.replayed=true",
        "PASS" if body.get("meta", {}).get("replayed") is True and
        body.get("data", {}).get("jobId") == job else "FAIL",
        "POST same key/content", code,
        f"replayed={body.get('meta', {}).get('replayed')} same_job="
        f"{body.get('data', {}).get('jobId') == job}")
    code, body, _ = I.http("POST", "/api/v1/system/echo-jobs", token=tok,
                           body={"message": "different", "numbersAsStrings": ["1"]},
                           headers={"Idempotency-Key": key})
    add("AB-08b", "T13 同键不同内容 → 409 冲突（非 200/假成功）",
        "PASS" if code == 409 and "CONFLICT" in body.get("error", {}).get("code", "") else "FAIL",
        "POST same key/different content", code, json.dumps(body)[:200])
    cp = I.worker_once(timeout=180)
    log = (REPORTS / "worker-once.log").read_text(encoding="utf-8", errors="replace")
    st = I.sql_scalar(f"SELECT status FROM async_jobs WHERE id='{job}'")
    processed = (job in log) or st in ("running", "succeeded")
    add("AB-06b", "worker --once 领取并处理本次 enqueued job（日志含 jobId 或状态推进）",
        "PASS" if cp.returncode == 0 and processed and st == "succeeded" else "FAIL",
        "python -m mvp_worker --once", cp.returncode, f"job={job[:8]} status={st}")
    code, body, _ = I.http("GET", f"/api/v1/system/echo-jobs/{job}", token=tok)
    d = body.get("data", {})
    add("AB-06c", "GET echo job → succeeded + attemptCount=1 + leaseRevision=1",
        "PASS" if code == 200 and d.get("status") == "succeeded"
        and d.get("attemptCount") == "1" and d.get("leaseRevision") == "1" else "FAIL",
        "GET /system/echo-jobs/{id}", code,
        f"status={d.get('status')} attempt={d.get('attemptCount')} lease={d.get('leaseRevision')}")
    # AB-11
    code, body, hdr = I.http("POST", "/api/v1/system/echo-jobs", token=tok, body={})
    rid = hdr.get("X-Request-Id")
    add("AB-11a", "非法输入 → 400 INVALID_INPUT 信封，X-Request-Id==body.requestId（均非空）",
        "PASS" if code == 400 and body.get("error", {}).get("code") == "INVALID_INPUT"
        and request_id_ok(rid, body) else "FAIL", "POST /system/echo-jobs {}", code,
        f"rid_hdr={rid} rid_body={body.get('requestId')}")
    code, body, _ = I.http("GET", "/api/v1/me/member-access-grants", token=tok)
    add("AB-11b", "业务 stub（有 token）→ 501 NOT_IMPLEMENTED，不给假 200",
        "PASS" if code == 501 and body.get("error", {}).get("code") == "NOT_IMPLEMENTED" else "FAIL",
        "GET /me/member-access-grants", code, json.dumps(body)[:200])
    code, body, _ = I.http("GET", f"/api/v1/system/echo-jobs/{uuid.uuid4()}", token=tok)
    add("AB-11c", "未知资源 → 404 结构化信封（含 requestId）",
        "PASS" if code == 404 and body.get("error") and body.get("requestId") else "FAIL",
        "GET /system/echo-jobs/<random>", code, json.dumps(body)[:200])


# ------------------------------------------------------------------ AB-07 / AB-06d runtime

def stage_ab07_lease():
    k = f"e-lease-{I.SUFFIX}"
    I.psql("INSERT INTO async_jobs (job_type,dedup_key,owner_type,owner_id,payload,status,"
           "lease_owner,lease_until,lease_revision,attempt_count,max_attempts) VALUES "
           f"('system.echo','{k}','system',gen_random_uuid(),'{{\"schema_version\":1}}','running',"
           "'stale-worker', now() - interval '5 minutes', 1, 1, 5)")
    cp = I.worker_cli("--recover", timeout=120)
    st = I.sql_scalar(f"SELECT status FROM async_jobs WHERE dedup_key='{k}'")
    lr = I.sql_scalar(f"SELECT lease_revision FROM async_jobs WHERE dedup_key='{k}'")
    own = I.sql_scalar(f"SELECT coalesce(lease_owner,'NULL') FROM async_jobs WHERE dedup_key='{k}'")
    add("AB-07a", "过期 running 租约回收 → queued + lease_revision+1 + 释放 owner（条件更新）",
        "PASS" if st == "queued" and lr == "2" and own == "NULL" else "FAIL",
        "worker --recover", cp.returncode, f"status={st} lease_revision={lr} owner={own}")


AB06D_SCRIPT = r'''
import json, sys, uuid
from sqlalchemy import text
from mvp_worker.config import WorkerConfig
from mvp_worker.db import create_db_engine
from mvp_worker.runtime.claim import claim_batch
from mvp_worker.runtime.expire import recover_expired
from mvp_worker.runtime.complete import StaleGeneration, complete_success

cfg = WorkerConfig()
engine = create_db_engine(cfg.runtime_dsn, pool_size=cfg.pool_size)
suffix = uuid.uuid4().hex[:8]
res = {}

def insert_job(dedup, max_attempts):
    with engine.begin() as c:
        return str(c.execute(text(
            "INSERT INTO async_jobs (job_type,dedup_key,owner_type,owner_id,payload,status,"
            "attempt_count,max_attempts) VALUES ('system.echo',:d,'system',gen_random_uuid(),"
            "jsonb_build_object('schema_version',1),'queued',0,:m) RETURNING id"),
            {"d": dedup, "m": max_attempts}).scalar_one())

def claim(jid):
    claims = claim_batch(engine, worker_id="e-w1", lease_seconds=60, batch_size=50)
    return next((c for c in claims if c.id == jid), None)

def row(jid):
    with engine.connect() as c:
        return dict(c.execute(text(
            "SELECT status, attempt_count, max_attempts, lease_revision, last_error, finished_at "
            "FROM async_jobs WHERE id=CAST(:i AS uuid)"), {"i": jid}).mappings().one())

def expire(jid):
    with engine.begin() as c:
        c.execute(text("UPDATE async_jobs SET lease_until=CURRENT_TIMESTAMP - interval '1 second'"
                       " WHERE id=CAST(:i AS uuid)"), {"i": jid})

# 1) 重试上限：max_attempts=1，claim 后崩溃 → 回收应 failed/RETRY_LIMIT_EXCEEDED，不再 requeue
j1 = insert_job(f"e-ab06d-ceiling-{suffix}", 1)
c1 = claim(j1)
expire(j1)
n1 = recover_expired(engine)
r1 = row(j1)
err1 = r1["last_error"] if isinstance(r1["last_error"], dict) else json.loads(r1["last_error"])
n1b = recover_expired(engine)
res["ceiling"] = {"claimed": c1 is not None, "recovered": n1, "status": r1["status"],
                  "attempt": int(r1["attempt_count"]), "max": int(r1["max_attempts"]),
                  "code": err1.get("code"), "retryable": err1.get("retryable"),
                  "second_recover": n1b}

# 2) 陈旧代次：claim(N) → SQL 过期 + recover(+1) → 旧代次 complete_success 拒绝且业务写回滚
j2 = insert_job(f"e-ab06d-stale-{suffix}", 5)
c2 = claim(j2)
expire(j2)
recover_expired(engine)
sentinel = str(uuid.uuid4())

def business_tx(conn):
    conn.execute(text("INSERT INTO media_objects (id,bucket,object_key,purpose,state) "
                      "VALUES (CAST(:i AS uuid),'e-ab06d','e/rollback/'||:i,'assessment_result',"
                      "'pending')"), {"i": sentinel})

raised = None
try:
    complete_success(engine, c2, handler_result_tx=business_tx)
    raised = "NO_RAISE"
except StaleGeneration:
    raised = "StaleGeneration"
with engine.connect() as c:
    sentinel_rows = c.execute(text("SELECT count(*) FROM media_objects "
                                   "WHERE id=CAST(:i AS uuid)"), {"i": sentinel}).scalar_one()
res["stale"] = {"raised": raised, "sentinel_rows": sentinel_rows,
                "old_revision": c2.lease_revision}
print("AB06D_RESULT " + json.dumps(res, ensure_ascii=False))
'''


def stage_ab06d_runtime():
    """陈旧代次同事务回滚 + 重试上限：E 驱动进程内导入真实 Worker 运行时 + E 专属 PG。
    运行时边界集成验证，非 HTTP 链路；受控回调仅存在于 E 驱动，不改 A 源码。"""
    script = REPORTS / "ab06d_runtime.py"
    script.write_text(AB06D_SCRIPT, encoding="utf-8")
    cp = I.run([str(I.PY), str(script)], cwd=I.WORKER_DIR,
               env={**I.WORKER_ENV, "PYTHONPATH": str(I.WORKER_DIR / "src")},
               timeout=300, log_name="ab06d-runtime.log")
    out = (cp.stdout or "") + (cp.stderr or "")
    payload = None
    for line in out.splitlines():
        if line.startswith("AB06D_RESULT "):
            payload = json.loads(line[len("AB06D_RESULT "):])
    if payload is None:
        add("AB-06d", "陈旧代次同事务回滚 + 重试上限（运行时边界集成）", "FAIL",
            "python ab06d_runtime.py (真实 runtime + E PG)", cp.returncode, _excerpt_cp(cp))
        return
    ceiling = payload.get("ceiling", {})
    stale = payload.get("stale", {})
    ok_ceiling = (ceiling.get("claimed") and ceiling.get("status") == "failed"
                  and ceiling.get("code") == "RETRY_LIMIT_EXCEEDED"
                  and ceiling.get("retryable") is False
                  and ceiling.get("attempt") == 1 and ceiling.get("second_recover") == 0)
    ok_stale = stale.get("raised") == "StaleGeneration" and stale.get("sentinel_rows") == 0
    add("AB-06d", "陈旧代次同事务回滚 + 重试上限（运行时边界集成，非 HTTP；受控回调在 E 驱动内）",
        "PASS" if ok_ceiling and ok_stale else "FAIL",
        "python ab06d_runtime.py（真实 mvp_worker runtime + E 专属 PG）", cp.returncode,
        f"ceiling={ceiling} stale={stale}")


# ------------------------------------------------------------------ N1 python

def stage_n1_python_layer():
    py = (
        "import sys; sys.path.insert(0,'%s')\n"
        "from mvp_worker.handlers.system_echo import EchoHandler\n"
        "h=EchoHandler()\n"
        "cases={'string':{'schema_version':'1'},'null':{'schema_version':None},"
        "'bool':{'schema_version':True},'fractional':{'schema_version':1.5},"
        "'negative':{'schema_version':-2},'unsupported':{'schema_version':99},"
        "'array':[1,2],'missing':{'message':'x'}}\n"
        "res=[]\n"
        "for k,v in cases.items():\n"
        "    try:\n"
        "        h.validate(v); res.append(k+':ACCEPT')\n"
        "    except Exception:\n"
        "        res.append(k+':REJECT')\n"
        "print(' '.join(res))\n"
    ) % (I.WORKER_DIR / "src")
    cp = I.run([str(I.PY), "-c", py], cwd=I.WORKER_DIR, env=I.WORKER_ENV, timeout=120,
               log_name="n1-python-validate.log")
    out = cp.stdout.strip()
    rejected = {"string", "null", "bool", "fractional", "negative", "unsupported", "array",
                "missing"}
    got_rej = {x.split(":")[0] for x in out.split() if x.endswith(":REJECT")}
    add("N1-py-schema", "Python echo payload schema：string/null/bool/1.5/-2/不支持版本/数组/缺字段拒绝",
        "PASS" if rejected <= got_rej else "FAIL", "python -c EchoHandler().validate(变体)",
        cp.returncode, out)
    keys = []
    for name, payload in [("frac", '{"schema_version":1.5}'), ("neg", '{"schema_version":-2}'),
                          ("ver99", '{"schema_version":99}')]:
        k = f"e-n1rt-{name}-{I.SUFFIX}"
        keys.append(k)
        I.psql("INSERT INTO async_jobs (job_type,dedup_key,owner_type,owner_id,payload,status) "
               f"VALUES ('system.echo','{k}','system',gen_random_uuid(),'{payload}','queued')")
    for _ in range(4):
        I.worker_once(timeout=180)
        sts = [I.sql_scalar(f"SELECT status FROM async_jobs WHERE dedup_key='{k}'") for k in keys]
        if all(x not in ("queued", "running") for x in sts):
            break
    states, ok2 = [], True
    for k in keys:
        st = I.sql_scalar(f"SELECT status FROM async_jobs WHERE dedup_key='{k}'")
        code = I.sql_scalar(f"SELECT coalesce(last_error->>'code','') FROM async_jobs "
                            f"WHERE dedup_key='{k}'")
        states.append(f"{k[-6:]}:{st}/{code}")
        ok2 = ok2 and st == "failed" and code == "UNSUPPORTED_CONTRACT"
    add("N1-py-runtime", "Python 运行时拒绝非法 schema_version（failed/UNSUPPORTED_CONTRACT，不循环）",
        "PASS" if ok2 else "FAIL", "worker --once 处理坏版本 job", "0/1", " ".join(states))


# ------------------------------------------------------------------ N2

def stage_n2_columns():
    w = I.psql("UPDATE async_jobs SET last_error='{\"message\":\"diag no version\"}' "
               f"WHERE dedup_key='e-lease-{I.SUFFIX}'")
    defs = I.sql_scalar(
        "SELECT string_agg(pg_get_constraintdef(oid),' | ') FROM pg_constraint "
        "WHERE conrelid IN ('async_jobs'::regclass,'media_objects'::regclass,"
        "'notifications'::regclass,'skin_assessments'::regclass,'care_plans'::regclass) "
        "AND contype='c'")
    diag = ["last_error", "failure_detail"]
    untouched = all(c not in defs for c in diag)
    add("N2-db", "五诊断列豁免：无 schema_version 可写；CHECK 定义不含这些诊断列",
        "PASS" if w.returncode == 0 and untouched else "FAIL",
        "UPDATE async_jobs.last_error 无版本 + 查 pg_constraint", w.returncode,
        f"no_check_on_diag_cols={untouched}")
    # 消费点分类检视：保留 file:line + 代码片段 + 读/写 + 分类；无法机械判定标“待人工复核”，
    # 存在待复核项则本子项降为 INFO（不计 PASS 依据）。
    cp = I.run(["grep", "-rnE", "last_error|failure_detail|lastError|failureDetail",
                str(I.JAVA_DIR / "src/main/java"), str(I.WORKER_DIR / "src")],
               timeout=120, log_name="n2-code-review-raw.log")
    rows = []
    for ln in cp.stdout.splitlines():
        m = re.match(r"^(.*?):(\d+):(.*)$", ln)
        if not m:
            continue
        path, lineno, snippet = m.group(1), m.group(2), m.group(3).strip()
        rel = path.split("/backend/", 1)[-1] if "/backend/" in path else path
        low = ln.lower()
        uncertain = False
        if "systemechocontroller" in low:
            cls, kind, note = "客户端投影", "read", "echo GET 投影 data.lastError（关联已确认 A 缺陷）"
        elif "complete.py" in low or "loop.py" in low:
            cls, kind, note = "写入（worker 诊断）", "write", "failed/last_error 写入路径"
        elif "last_error" in low or "failure_detail" in low or "lasterror" in low:
            cls, kind, note = "其他", "review", "待人工复核"
            uncertain = True
        else:
            cls, kind, note = "仅日志/注释", "review", "待人工复核"
            uncertain = True
        rows.append({"loc": f"{rel}:{lineno}", "snippet": snippet[:160], "kind": kind,
                     "cls": cls, "note": note, "uncertain": uncertain})
    has_projection = any(r["cls"] == "客户端投影" for r in rows)
    uncertain_n = sum(1 for r in rows if r["uncertain"])
    d = I.out_logs()
    d.mkdir(parents=True, exist_ok=True)
    md = ["# N2 诊断列消费点分类检视（file:line + 片段 + 读/写 + 分类）", "",
          f"命中 {len(rows)} 处；待人工复核 {uncertain_n} 处；含客户端投影={has_projection}。",
          "分类规则：SystemEchoController→客户端投影(read)；worker complete/loop→写入；"
          "其余机械不可判定→待人工复核（本子项降 INFO）。", "",
          "| 文件:行 | 代码片段 | 读/写 | 分类 | 备注 |", "|---|---|---|---|---|"]
    md += [f"| {r['loc']} | `{r['snippet']}` | {r['kind']} | {r['cls']} | {r['note']} |"
           for r in rows]
    (d / "n2-code-review.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    status = "PASS" if rows and has_projection and uncertain_n == 0 else "INFO"
    add("N2-codereview", f"诊断列消费点分类检视（{len(rows)} 处，待人工复核 {uncertain_n} 处，"
                         f"客户端投影={has_projection}）", status,
        "grep Java/Python src + file:line/片段/分类记录", cp.returncode,
        f"hits={len(rows)} uncertain={uncertain_n} 详见 logs/n2-code-review.md"
        + ("（有未判定项，降为 INFO，不作为 PASS 依据）" if status == "INFO" else ""))


N2_LAST_ERROR_LIMIT = 1000


def n2_http_verdict(status, target_job, body, marker=None, limit=N2_LAST_ERROR_LIMIT):
    """N2-http 纯判定：返回 (verdict, reason)。True=PASS，False=FAIL，None=BLOCKED。

    PASS 仅当：HTTP 200 + data.id==目标 job + lastError 为空/已脱敏且在限内。
    任何错误路径（非 200、目标不符、缺字段、marker 回显、超长）绝不 PASS。
    """
    if status != 200:
        return None, f"HTTP {status}（未取得目标资源，不能判定投影）"
    data = (body or {}).get("data") or {}
    got_id = data.get("jobId", data.get("id"))  # echo GET 投影字段为 jobId
    if str(got_id or "") != str(target_job):
        return False, f"data.jobId={got_id!r} 与目标 job 不符"
    if "lastError" not in data:
        # 保守：字段缺失视为投影形态未知（BLOCKED，绝不导致总体通过）。若 A 未来按公共
        # 契约删除该字段，须先经契约确认再调整本预期（届时应在契约变更评审中同步）。
        return None, "响应缺 data.lastError 字段（投影形态未知，保守判 BLOCKED）"
    le = data.get("lastError")
    if le is None:
        return True, "本样本响应未暴露诊断内容（lastError=null）"
    blob = json.dumps(le, ensure_ascii=False)
    if marker and marker in blob:
        return False, f"marker 原样回显（len={len(blob)}）"
    if len(blob) > limit:
        return False, f"未限大小（len={len(blob)} > {limit}）"
    return True, f"本样本未回显 marker 且在限内（len={len(blob)}）；不构成通用脱敏保证"


def stage_n2_http():
    """N2-http 实测：SQL(断言 rc/影响行数) + GET(断言 200/目标 job) → 判定投影形态。"""
    job = CTX.get("job")
    if not job:
        add("N2-http", "诊断列 HTTP 投影实测", "BLOCKED", "依赖 echo job", "n/a",
            blocked="AB-06a 未产出 jobId，无法实测")
        return
    marker = "Bearer E2E_DIAG_SECRET_MARKER_12345"
    # 复现 SQL 用 jsonb_build_object/repeat 生成精简且**完整可执行**的语句（不截断）。
    variants = [
        ("marker", "jsonb_build_object('code','E_DIAG_MARKER','message',"
                   f"'{marker}','retryable',false)"),
        ("long", "jsonb_build_object('code','E_DIAG_LONG','message',repeat('L',4000),"
                 "'retryable',false)"),
    ]
    verdicts, repro = [], [f"jobId={job}（合成数据，无真实凭据）"]
    http_codes = []
    for name, err_sql in variants:
        sql = (f"WITH u AS (UPDATE async_jobs SET last_error={err_sql} "
               f"WHERE id='{job}' RETURNING id) SELECT count(*) FROM u")
        cp = I.psql(sql)
        rows = cp.stdout.strip()
        if cp.returncode != 0 or rows != "1":
            verdicts.append((None, f"{name}: 诊断 UPDATE 失败 rc={cp.returncode} rows={rows!r}"))
            repro.append(f"SQL[{name}]: {sql}\n-> rc={cp.returncode} rows={rows!r}")
            continue
        code, body, _ = I.http("GET", f"/api/v1/system/echo-jobs/{job}", token=CTX["token"])
        http_codes.append(str(code))
        v, why = n2_http_verdict(code, job, body, marker if name == "marker" else None)
        le = (body.get("data") or {}).get("lastError")
        le_blob = json.dumps(le, ensure_ascii=False) if le is not None else ""
        verdicts.append((v, f"{name}: {why}"))
        repro.append(
            f"SQL[{name}]（完整可执行）: {sql}\n"
            f"curl --noproxy '*' -H 'Authorization: Bearer <token>' "
            f"{APP_BASE}/api/v1/system/echo-jobs/{job} -> http={code}\n"
            f"data.lastError[:400]={le_blob[:400]!r}\n"
            f"len={len(le_blob)} marker_echoed={(marker in le_blob)}\n")
    d = I.out_logs()
    d.mkdir(parents=True, exist_ok=True)
    (d / "n2-http-repro.txt").write_text("\n".join(repro) + "\n", encoding="utf-8")
    if any(v is False for v, _ in verdicts):
        status = "FAIL"
    elif any(v is None for v, _ in verdicts):
        status = "BLOCKED"
    else:
        status = "PASS"
    add("N2-http", "诊断列 HTTP 投影：须脱敏/限大小/不原样返回（实测 data.lastError）",
        status, "诊断 UPDATE RETURNING count==1 + GET 断言 200/目标 job → 判定",
        "/".join(http_codes) or "n/a", " | ".join(w for _, w in verdicts),
        doubles="n/a")


# ------------------------------------------------------------------ N3 media

def stage_n3_media(s):
    tok, acct = s["access"], s["accountId"]
    # 真实上传者主体（T13 canonical = <account_uuid>:<installation_id>）
    uploader_ref = f"{acct}:{s['installationId']}"
    mid = str(uuid.uuid4())
    face = str(uuid.uuid4())
    I.psql("INSERT INTO media_objects (id,bucket,object_key,purpose,state,uploader_type,"
           f"uploader_ref,content_type,byte_size,storage_metadata) VALUES ('{mid}','e-bucket',"
           f"'e/n3-{I.SUFFIX}.bin','assessment_source','available','app','{uploader_ref}',"
           f"'application/octet-stream',5,'{{\"schema_version\":1}}')")
    I.psql("INSERT INTO media_objects (id,bucket,object_key,purpose,state,uploader_type,"
           f"uploader_ref,storage_metadata) VALUES ('{face}','e-bucket','e/n3f-{I.SUFFIX}.bin',"
           f"'grant_face','available','app','{uploader_ref}','{{\"schema_version\":1}}')")
    code, body, _ = I.http("GET", f"/api/v1/media/{mid}/content", token=tok)
    ok1 = code == 404 and body.get("error", {}).get("code") == "RESOURCE_NOT_VISIBLE"
    code2, body2, _ = I.http("GET", f"/api/v1/media/{face}/content", token=tok)
    ok2 = code2 == 404 and body2.get("error", {}).get("code") == "RESOURCE_NOT_VISIBLE"
    ok3 = code != 403 and code2 != 403
    add("N3-media", "媒体 deny-all：任何 GET 统一 404（含 face purpose、含真实上传者本人、无 403 泄露）",
        "PASS" if ok1 and ok2 and ok3 else "FAIL", "真实上传者主体 GET /media/{id}/content",
        f"{code}/{code2}", f"uploader_self_404={ok1 and ok2} no_403={ok3} uploader={acct[:8]}")


# ------------------------------------------------------------------ cleanup + settlement

def cleanup():
    I.stop_java()
    I.stop_worker()
    cleanup_ok = True
    try:
        I.remove_container()
    except Exception as exc:
        cleanup_ok = False
        add("CLEANUP", "停 Java/worker、按 run 标签删除本 run 的 mvp-e-pg",
            "FAIL", "ownership-guarded docker rm", "1", str(exc))
    if "CLEANUP" not in {r["id"] for r in R.rows}:
        add("CLEANUP", "停 Java/worker、按 run 标签删除本 run 的 mvp-e-pg",
            "PASS" if cleanup_ok and not I.container_exists() else "FAIL",
            "docker rm -f -v mvp-e-pg (label mvp.e.run)", "0", "")
    freed = I.port_free(I.APP_PORT) and I.port_free(I.WORKER_HEALTH_PORT) \
        and I.port_free(I.PG_HOST_PORT)
    add("CLEANUP-ports", f"端口释放：18081 free={I.port_free(I.APP_PORT)} "
                         f"18082 free={I.port_free(I.WORKER_HEALTH_PORT)} "
                         f"55433 free={I.port_free(I.PG_HOST_PORT)}",
        "PASS" if freed else "FAIL", "ss probe", "0", "")


KNOWN_STATUSES = ("PASS", "FAIL", "BLOCKED", "INFO")


def settlement(expected: frozenset = EXPECTED_CHECKS):
    ids = [r["id"] for r in R.rows]
    dup = sorted({x for x in ids if ids.count(x) > 1})
    settled = set(ids)
    missing = sorted(expected - settled)
    extra = sorted(settled - expected)
    statuses = [r["status"] for r in R.rows]
    unknown = sorted({s for s in statuses if s not in KNOWN_STATUSES})
    counts = {name.lower(): sum(1 for s in statuses if s == name) for name in KNOWN_STATUSES}
    return {"ids": ids, "settled": len(settled), "rows": len(ids),
            "expected": len(expected), "missing": missing, "extra": extra,
            "duplicates": dup, "unknown_status": unknown, "counts": counts,
            "pass": counts["pass"], "fail": counts["fail"],
            "blocked": counts["blocked"], "info": counts["info"]}


def settlement_complete(settle: dict) -> bool:
    """结算完整 = 无缺项/多项/重复/未知状态，且各合法状态计数之和==结算行数。"""
    return (not settle.get("missing") and not settle.get("extra")
            and not settle.get("duplicates") and not settle.get("unknown_status")
            and sum(settle["counts"].values()) == settle.get("rows", -1))


def final_exit(formal: bool, settle: dict) -> int:
    """退出码：0=结算完整且无 FAIL 无 BLOCKED（INFO 为附条件接受，须显式披露）；
    1=有 FAIL 或有 BLOCKED；4=结算不完整/缺项/多项/重复/未知状态（正式模式）。
    诊断模式（PARTIAL，不落 evidence）：有 FAIL/BLOCKED→1，否则 0，不判 4。"""
    if settle.get("unknown_status"):
        return 4
    if settle.get("fail", 0) > 0 or settle.get("blocked", 0) > 0:
        return 1
    if formal and not settlement_complete(settle):
        return 4
    return 0


def save_log_excerpts():
    LOGS = I.out_logs()
    LOGS.mkdir(parents=True, exist_ok=True)

    def excerpt(name, pattern=None, tail=20):
        p = REPORTS / name
        if not p.exists():
            return
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if pattern:
            lines = [ln for ln in lines if pattern in ln]
        if not lines:
            lines = ["(no matching line)"]
        (LOGS / f"{name}.excerpt.txt").write_text("\n".join(lines[-tail:]), encoding="utf-8")

    excerpt("java-app-2.log", "No migration necessary")
    excerpt("worker-once.log", tail=8)
    excerpt("mvn-targeted-tests.log", "Tests run", tail=5)
    excerpt("worker-check.log", tail=3)
    excerpt("ab02d-worker-pytest.log", tail=4)
    excerpt("ab06d-runtime.log", tail=6)
    for p in sorted(REPORTS.glob("java-prod-*.log")):
        excerpt(p.name, "production fail-closed", tail=3)


def conclusion_line(settle: dict) -> str:
    """结论三态：未通过（FAIL/BLOCKED/结算不完整/未知状态）/ 通过（附条件，有 INFO）/ 通过。"""
    if settle.get("unknown_status"):
        return f"**A 基础验收结论：拒绝**——出现未知状态 {settle['unknown_status']}，不得判定通过。"
    if settle.get("fail", 0) > 0 or settle.get("blocked", 0) > 0:
        return (f"**A 基础验收结论：未通过**——{settle['fail']} 项 FAIL / {settle['blocked']} 项 "
                "BLOCKED（见下）；待 A 修复后绑定新 A SHA 定向重验；在此之前不得表述为"
                "“A 已通过验收”。")
    if not settlement_complete(settle):
        return (f"**A 基础验收结论：未通过**——结算不完整（missing={settle['missing']} "
                f"extra={settle['extra']} duplicates={settle['duplicates']}），不得判定通过。")
    if settle.get("info", 0) > 0:
        ids = [r["id"] for r in R.rows if r["status"] == "INFO"]
        return (f"**A 基础验收结论：通过（附条件）**——{settle['info']} 项 INFO 待人工复核"
                f"（{ids}），已有自动化项 0 FAIL / 0 BLOCKED；附条件项须人工复核后方可视为完成。")
    return "**A 基础验收结论：通过**（0 FAIL / 0 BLOCKED / 0 INFO）。"


def write_outputs(formal: bool, settle: dict, rc: int):
    result = {"schema": "e-acceptance-a-baseline/1", "run_id": I.RUN_ID,
              "mode": "formal" if formal else "diagnostic(PARTIAL)",
              "baseline": BASELINE, "expected": settle["expected"],
              "settled": settle["settled"], "missing": settle["missing"],
              "extra": settle["extra"], "duplicates": settle["duplicates"],
              "unknown_status": settle.get("unknown_status", []),
              "counts": {"pass": settle["pass"], "fail": settle["fail"],
                         "blocked": settle["blocked"], "info": settle["info"]},
              "counts_sum": sum(settle["counts"].values()), "rows": settle.get("rows"),
              "final_exit": rc, "results": R.rows}
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    if not formal:
        print(f"[PARTIAL 诊断模式] 未结算 {len(settle['missing'])} 项；只写 reports/，不落 evidence/")
        return
    EVID = I.out_evidence()
    EVID.mkdir(parents=True, exist_ok=True)
    save_log_excerpts()
    p, f, b, n = settle["pass"], settle["fail"], settle["blocked"], settle["info"]
    lines = [
        f"# E 独立 A 基线验收证据（{I.DATE_UTC}，run {I.RUN_ID}）",
        "",
        "候选基线（config/baseline.json）："
        f"code={BASELINE.get('candidate_code_sha')} report={BASELINE.get('report_head')} "
        f"dev={BASELINE.get('isolated_dev')} integrated={BASELINE.get('integrated_head')} "
        f"oracle={BASELINE.get('a_oracle')}",
        "",
        f"环境：E 专用 PG `{I.PG_CONTAINER}`@127.0.0.1:{I.PG_HOST_PORT}（label mvp.e.run={I.RUN_ID}，"
        f"镜像 {I.PG_IMAGE}），Java@{I.APP_PORT}，worker 健康@{I.WORKER_HEALTH_PORT}；"
        "94 业务场景保持 dependency_pending（B/C/D 未集成）。",
        "",
        "**测试替身标注**：A dev/test 形态使用隔离替身（InMemory 会话 / SMS 固定码 123456 / "
        "DB 对照云台凭据 / 文件系统存储），结果均为 `doubles_pass` 语义，"
        "**不宣称真实供应商或真实设备接入**。",
        "",
        "**运行时边界集成验证**：AB-06d 使用 E 驱动进程内导入的真实 `mvp_worker` runtime + "
        "E 专属 PG + 受控测试回调，**非 HTTP 链路**，不改 A 源码。",
        "",
        f"## 结算：{settle['settled']}/{settle['expected']} 唯一结算；"
        f"{p} PASS / {f} FAIL / {b} BLOCKED / {n} INFO（计数和={sum(settle['counts'].values())}"
        f"==行数 {settle.get('rows')}）；final_exit={rc}",
        "",
        (f"结算缺口：missing={settle['missing']} extra={settle['extra']} "
         f"duplicates={settle['duplicates']} unknown={settle.get('unknown_status')}"),
        "",
        conclusion_line(settle),
        "",
        "| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |",
        "|---|---|---|---|---|",
    ]
    for r in R.rows:
        lines.append(f"| {r['id']} | {r['title']} | **{r['status']}** | "
                     f"{r['command']} / {r['rc']} | {r['excerpt']} |")
    infos = [r for r in R.rows if r["status"] == "INFO"]
    lines += ["", "## INFO 附条件项（待人工复核）", ""]
    if not infos:
        lines.append("（无）")
    for r in infos:
        lines.append(f"- **{r['id']}** {r['title']}；{r['excerpt']}")
    fails = [r for r in R.rows if r["status"] == "FAIL"]
    lines += ["", "## A 缺陷清单（如实；未修 A 源码）", ""]
    if not fails:
        lines.append("（无 FAIL 项）")
    for r in fails:
        lines.append(f"- **{r['id']}** {r['title']}；命令={r['command']}；rc={r['rc']}；"
                     f"摘录={r['excerpt']}")
    lines += ["", "## 逐项细节与边界", "",
              "- N1 Java 服务层：`SchemaVersionBoundaryTest`（真实 IdempotencyService."
              "ensureSchemaVersion 类：缺省注入 1/显式整数/null/字符串/小数/非对象 → 400 "
              "INVALID_INPUT）；HTTP 层无可由客户端控制的 schema_version 输入（echo 摘要由"
              "服务端注入整数 1），故服务层用真实类测试验证。",
              "- N1 Python 服务层：`EchoHandler.validate` targeted 直调 + 真实运行时坏版本 job "
              "→ failed/UNSUPPORTED_CONTRACT。",
              "- N1 DB 已知限制：object+number CHECK 放行小数/负数 JSON number，由服务层兜底"
              "（A 报告未决项 9）。",
              "- AB-02d：E 定向执行与基础/恢复/版本直接相关的 worker 测试文件（见命令），"
              "DSN 指向 E 专属 PG 临时库（MVP_A_PG_CONTAINER=mvp-e-pg / HOST_PORT=55433），"
              "绝不混用 A 库/容器；与本轮无关的全量重跑按'避免重复无关单测'排除。",
              "- AB-06d：运行时边界集成验证（claim/recover/complete 公共运行时 + E PG + "
              "E 驱动内受控 business_tx 哨兵），非 HTTP；未改 A 源码。",
              "- AB-10 黑盒启动拒绝（缺真实提供方/unsafe media）与 targeted "
              "ProductionFailClosedTest（媒体开关）在 AB-10a-c 与 AB-09a/N1j 分列陈述。",
              f"- 证据日志：reports/{I.RUN_ID}/ 与 logs/ 摘录（非空）。",
              "- A 缺陷：见上表 FAIL 项与上方“A 缺陷清单”；本轮未修 A 源码。",
              "- 清理：按 label 归属删除 mvp-e-pg，Java/worker 进程与端口释放。",
              ""]
    (EVID / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    (EVID / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    print(f"\n=== E A-baseline: {p} PASS / {f} FAIL / {b} BLOCKED / {n} INFO "
          f"(settled {settle['settled']}/{settle['expected']}, exit={rc}) ===")
    print(conclusion_line(settle))
    print(f"evidence: {EVID}/summary.md")


# ------------------------------------------------------------------ main

def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    only = {s.strip() for s in os.environ.get("E_AB_ONLY", "").split(",") if s.strip()}
    formal = not only
    I.set_output_mode(formal)  # 入口一次性决定全部输出目录（诊断只写 reports/）

    def want(name: str) -> bool:
        return not only or name in only

    # 提前置失败（锁/端口/残留容器）不写 evidence；退出码由结算门禁统一决定，绝不在
    # finally 重算前 return 定格。
    ok_lock, why = I.acquire_single_instance_lock()
    if not ok_lock:
        print(f"[FATAL] {why}；本次不启动、不写 evidence")
        return 4
    try:
        ports = I.check_ports()
        if not all(ports.values()):
            add("SETUP-ports", "三端口启动前检查", "FAIL", "ss", "1", str(ports))
        elif I.container_exists():
            add("SETUP", "无同名 E 容器残留", "FAIL", "docker inspect", "1",
                f"{I.PG_CONTAINER} 已存在且非本 run；拒绝覆盖")
        else:
            cp = I.start_pg()
            add("SETUP-pg", f"启动 E 专用 PG（{I.PG_CONTAINER}@{I.PG_HOST_PORT}，label=本 run）",
                "PASS" if cp.returncode == 0 and I.wait_pg() else "FAIL",
                "docker run --label mvp.e.run=... postgres:16", cp.returncode,
                _excerpt_cp(cp) if cp.returncode else "UP")
            if cp.returncode == 0:
                I.recreate_db()
                if want("build"):
                    stage_build_and_language()
                if want("ab10"):
                    stage_ab10_failclosed()
                if want("ab01"):
                    I.recreate_db()
                    stage_ab01_restart_and_ab03()
                elif not I.java_alive():
                    I.start_java(log_name="java-app-1.log")
                if want("ab02"):
                    stage_ab02_worker()
                if want("ab02d"):
                    stage_ab02d_targeted_pytest()
                if want("n1sql"):
                    stage_n1_sql_boundary()
                if want("ab04"):
                    stage_ab04_constraints()
                s = None
                if want("ab0508"):
                    s = stage_ab05_auth()
                if want("ab0608") or want("n2http") or want("n3"):
                    if s is None:
                        s = login() or {}
                    CTX["token"] = s.get("access", "")
                    if s and want("ab0608"):
                        stage_ab0608_echo(s)
                    if want("n2http"):
                        stage_n2_http()
                    if s and want("n3"):
                        stage_n3_media(s)
                if want("ab07"):
                    stage_ab07_lease()
                if want("ab06d"):
                    stage_ab06d_runtime()
                if want("n1py"):
                    stage_n1_python_layer()
                if want("n2"):
                    stage_n2_columns()
    finally:
        try:
            cleanup()
        finally:
            I.release_single_instance_lock()
        settle = settlement()
        rc = final_exit(formal, settle)
        write_outputs(formal, settle, rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
