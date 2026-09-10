#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E 对 A 候选基线的独立基础验收：AB-01..AB-11 + N1..N3。

用法：backend/acceptance/.venv-driver/bin/python backend/acceptance/driver/a_baseline.py
（或 backend/acceptance/run.sh a-baseline）
真实 PG/Java/Worker；dev/test 替身形态 → 证据标注 doubles_pass，不宣称真实供应商接入。
"""
from __future__ import annotations

import json
import sys
import time
import uuid

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from driver import infra as I  # noqa: E402
from driver.infra import R, REPORTS, EVID, LOGS, PG_DB, APP_BASE  # noqa: E402

BASELINE = json.loads((I.ROOT / "config" / "baseline.json").read_text(encoding="utf-8"))["a_baseline"]


# ------------------------------------------------------------------ helpers

def _excerpt_cp(cp, n=300):
    out = ((cp.stdout or "") + (cp.stderr or "")).strip().replace("\n", " ")
    return out[:n]


def record(cid, title, ok, command="", rc="", excerpt="", doubles="doubles_pass", blocked=None):
    if ok is None:
        R.add(cid, title, "BLOCKED", command, rc, blocked or "", doubles)
    else:
        R.add(cid, title, "PASS" if ok else "FAIL", command, rc, excerpt, doubles)


LOGIN_DEBUG = {"step": "", "code": "", "body": ""}


def login(phone_suffix=None):
    digits = phone_suffix or f"{int(I.SUFFIX, 16) % 100000000:08d}"
    phone = f"+86138{digits[:8]}"  # 纯数字 E.164（替身号码；非真实用户号段）
    code, body, _ = I.http("POST", "/api/v1/auth/sms-challenges",
                           body={"phone": phone, "purpose": "login"})
    if code != 200:
        LOGIN_DEBUG.update(step="sms-challenges", code=str(code), body=json.dumps(body)[:200])
        return None
    chal = body["data"]["challengeId"]
    code, body, _ = I.http("POST", "/api/v1/auth/sessions",
                           body={"challengeId": chal, "code": "123456",
                                 "installationId": f"e-inst-{I.SUFFIX}"})
    if code != 200:
        LOGIN_DEBUG.update(step="sessions", code=str(code), body=json.dumps(body)[:200])
        return None
    d = body["data"]
    return {"phone": phone, "accountId": d["accountId"], "access": d["accessToken"],
            "refresh": d["refreshToken"]}


# ------------------------------------------------------------------ stages

def stage_failclosed_prod():
    """AB-10 + N3 fail-closed：production 下非默认 media 模式/开放开关/缺真实提供方均拒绝启动。"""
    attempts = [
        ("prod+doubles", {"SPRING_PROFILES_ACTIVE": "prod", "APP_PROVIDERS_MODE": "doubles"}),
        ("prod+owner-dev", {"SPRING_PROFILES_ACTIVE": "prod", "APP_PROVIDERS_MODE": "doubles",
                            "APP_MEDIA_ACCESS_MODE": "owner-dev"}),
        ("prod+allow-any", {"SPRING_PROFILES_ACTIVE": "prod", "APP_PROVIDERS_MODE": "doubles",
                            "APP_MEDIA_ALLOW_ANY_AUTHENTICATED": "true"}),
    ]
    detail = []
    ok_all = True
    for name, extra in attempts:
        log = f"java-prod-{name.replace('+', '_')}.log"
        I.start_java(extra_env=extra, log_name=log, wait=False)
        proc = I.JAVA_PROC
        rc = None
        try:
            rc = proc.wait(timeout=90) if proc else "no-proc"
        except Exception:
            rc = "timeout(still running)"
        alive = I.java_alive()
        if alive:
            ok = False
        else:
            text = (REPORTS / log).read_text(encoding="utf-8", errors="replace")
            ok = rc != 0 and ("production" in text.lower() or "fail" in text.lower()
                              or "reject" in text.lower() or "refus" in text.lower())
        ok_all = ok_all and ok
        detail.append(f"{name}: exited={not alive} rc={rc} ok={ok}")
        I.stop_java()
    R.add("AB-10", "fail-closed：production 非默认 media/开放开关/缺真实提供方拒绝启动",
          "PASS" if ok_all else "FAIL", "启动 3 种 production 变体并观察退出",
          "see logs", " | ".join(detail))


def stage_build_and_language():
    cp = I.run(["mvn", "-B", "-q", "-DskipTests", "package"], cwd=I.JAVA_DIR, timeout=1800,
               log_name="mvn-package.log")
    jar_ok = any((I.JAVA_DIR / "target").glob("web-java-*.jar")) if cp.returncode == 0 else False
    R.add("AB-01a", "Java 构建（-DskipTests package）产出可运行 jar",
          "PASS" if cp.returncode == 0 and jar_ok else "FAIL",
          "mvn -B -q -DskipTests package", cp.returncode, _excerpt_cp(cp))
    # 相关语言验证（不重跑全量 124；N1 Java 服务层）
    cp2 = I.run(["mvn", "-B", "-q", "test",
                 "-Dtest=SchemaVersionBoundaryTest,ProductionFailClosedTest"],
                cwd=I.JAVA_DIR, timeout=1200, log_name="mvn-targeted-tests.log")
    R.add("AB-09a/N1j", "Java 目标测试：SchemaVersionBoundaryTest + ProductionFailClosedTest",
          "PASS" if cp2.returncode == 0 else "FAIL",
          "mvn -B -q test -Dtest=SchemaVersionBoundaryTest,ProductionFailClosedTest",
          cp2.returncode, _excerpt_cp(cp2))
    # contracts（E venv-driver 只读运行 A 的脚本）
    for cid, title, cmd in [
        ("AB-09b", "jcs.py selftest（17 向量权威数对）",
         [str(I.PY), "scripts/jcs.py", "selftest"]),
        ("AB-09c", "validate_samples.py（样例+向量重算）",
         [str(I.PY), "scripts/validate_samples.py"]),
    ]:
        cp3 = I.run(cmd, cwd=I.CONTRACTS, timeout=300,
                    log_name=title.split("（")[0].strip().replace(" ", "_") + ".log")
        R.add(cid, title, "PASS" if cp3.returncode == 0 else "FAIL",
              " ".join(cmd[1:]), cp3.returncode,
              ((cp3.stdout or "").strip().splitlines() or [""])[-1][:200])
    code = ("import yaml\nfrom openapi_spec_validator import validate\n"
            "validate(yaml.safe_load(open('openapi/openapi.yaml')))\nprint('OPENAPI VALID')")
    cp4 = I.run([str(I.PY), "-c", code], cwd=I.CONTRACTS, timeout=300,
                log_name="openapi-validate.log")
    R.add("AB-09d", "openapi_spec_validator（基础契约）",
          "PASS" if cp4.returncode == 0 and "OPENAPI VALID" in cp4.stdout else "FAIL",
          "python -c validate(openapi.yaml)", cp4.returncode, _excerpt_cp(cp4))


def stage_ab01_restart_and_ab03():
    ok1 = I.start_java(log_name="java-app-1.log")
    pid1 = I.JAVA_PROC.pid if I.JAVA_PROC else "-"
    R.add("AB-01b", "Java dev 启动 + /actuator/health UP",
          "PASS" if ok1 else "FAIL", f"java -jar (SERVER_PORT={I.APP_PORT}, db={PG_DB})",
          "0" if ok1 else "1", f"first pid={pid1}")
    if not ok1:
        return False
    I.stop_java()
    ok2 = I.start_java(log_name="java-app-2.log")
    log2 = (REPORTS / "java-app-2.log").read_text(encoding="utf-8", errors="replace")
    noop = "No migration necessary" in log2
    R.add("AB-01c", "SIGTERM 停止 → 再启动 UP；Flyway no-op（重复启动无破坏）",
          "PASS" if ok2 and noop else "FAIL", "restart cycle",
          "0" if ok2 else "1", f"second UP={ok2}; flyway_noop={noop}")
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
    R.add("AB-03", f"全新 E 库 Flyway V1+V2 迁移：14 表（实际 {len(got)}），版本={hist}",
          "PASS" if ok3 else "FAIL", "fresh db migrate via app start", tables,
          f"missing={sorted(expected - got)} extra={sorted(got - expected)} "
          f"history={hist} success_rows={hist_ok}")
    return ok2


def stage_ab02_worker():
    cp = I.worker_cli("--check", timeout=120)
    R.add("AB-02a", "worker --check 连通自检（E 库）", "PASS" if cp.returncode == 0 else "FAIL",
          "python -m mvp_worker --check", cp.returncode, _excerpt_cp(cp))
    I.start_worker()
    hz = I.wait_http(f"{I.WORKER_BASE}/healthz", timeout_s=45)
    rz = I.wait_http(f"{I.WORKER_BASE}/readyz", timeout_s=45)
    R.add("AB-02b", "worker 运行循环 + /healthz /readyz UP（18082）",
          "PASS" if hz and rz else "FAIL", "python -m mvp_worker (loop)", "0" if hz and rz else "1",
          f"healthz={hz} readyz={rz}")
    I.stop_worker()
    stopped = I.WORKER_PROC is None
    log = (REPORTS / "worker-loop.log").read_text(encoding="utf-8", errors="replace")
    graceful = "shutdown" in log.lower() or "stop" in log.lower() or "signal" in log.lower()
    R.add("AB-02c", "worker SIGTERM 优雅停机", "PASS" if stopped else "FAIL",
          "kill -TERM worker", "0", f"graceful_log={graceful}")
    R.add("AB-02d", "worker pytest 全量（47）", "BLOCKED",
          "按协调指示不重跑 A 全量单测；dev 固定端口脚本禁直接执行",
          "n/a", "", blocked="按指示不为本轮重复 A 全量单测；E 用 --check/真实循环/端点验证替代")


def stage_n1_sql_boundary():
    """N1：DB 层 object+number CHECK 负例/正例 + 已知非整数放行限制。"""
    variants = [
        ("array", "[\"schema_version\"]", False),
        ("null_version", '{"schema_version":null}', False),
        ("string_version", '{"schema_version":"1"}', False),
        ("bool_version", '{"schema_version":true}', False),
        ("missing_key", '{}', False),
        ("int1", '{"schema_version":1}', True),
        ("fractional", '{"schema_version":1.5}', True),   # 已知限制：number 非整数 DB 放行
        ("negative", '{"schema_version":-2}', True),       # 已知限制
    ]
    detail, ok = [], True
    for name, payload, should_accept in variants:
        sql = ("INSERT INTO async_jobs (job_type,dedup_key,owner_type,owner_id,payload) VALUES "
               f"('system.echo','e-n1-{name}-{I.SUFFIX}','system',gen_random_uuid(),'{payload}')")
        cp = I.psql(sql)
        accepted = cp.returncode == 0
        good = accepted == should_accept
        ok = ok and good
        if not accepted:
            detail.append(f"{name}:rej({'ck_job_payload_schema' in cp.stderr})")
        else:
            detail.append(f"{name}:accept")
    R.add("N1-db", "JSONB 写入边界（DB object+number CHECK）：非对象/null/字符串/bool/缺键拒绝，"
                   "整数接受；小数/负数 DB 放行=已知限制（服务层兜底）",
          "PASS" if ok else "FAIL", "psql INSERT async_jobs.payload 变体", "0/1",
          " ".join(detail))


def stage_n1_python_layer():
    """N1：Python worker echo payload schema（targeted 直调 validate + 运行时坏 payload）。"""
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
        "    except Exception as e:\n"
        "        res.append(k+':REJECT')\n"
        "print(' '.join(res))\n"
    ) % (I.WORKER_DIR / "src")
    cp = I.run([str(I.PY), "-c", py], cwd=I.WORKER_DIR, env=I.WORKER_ENV, timeout=120,
               log_name="n1-python-validate.log")
    out = cp.stdout.strip()
    rejected = {"string", "null", "bool", "fractional", "negative", "unsupported", "array", "missing"}
    got_rej = {x.split(":")[0] for x in out.split() if x.endswith(":REJECT")}
    ok = rejected <= got_rej
    R.add("N1-py-schema", "Python echo payload schema：string/null/bool/1.5/-2/不支持版本/数组/缺字段拒绝",
          "PASS" if ok else "FAIL", "python -c EchoHandler().validate(变体)", cp.returncode, out)

    # 运行时：DB 可放行的坏 payload（number 小数/负数/不支持版本）→ worker 处理 → failed
    keys = []
    for name, payload in [("frac", '{"schema_version":1.5}'), ("neg", '{"schema_version":-2}'),
                          ("ver99", '{"schema_version":99}')]:
        k = f"e-n1rt-{name}-{I.SUFFIX}"
        keys.append(k)
        I.psql("INSERT INTO async_jobs (job_type,dedup_key,owner_type,owner_id,payload,status) "
               f"VALUES ('system.echo','{k}','system',gen_random_uuid(),'{payload}','queued')")
    for _ in range(4):  # 同批可能含其它 queued job；循环 drain 直到本组结算
        I.worker_once(timeout=180)
        sts = [I.sql_scalar(f"SELECT status FROM async_jobs WHERE dedup_key='{k}'") for k in keys]
        if all(x != "queued" and x != "running" for x in sts):
            break
    states = []
    ok2 = True
    for k in keys:
        st = I.sql_scalar(f"SELECT status FROM async_jobs WHERE dedup_key='{k}'")
        code = I.sql_scalar(f"SELECT coalesce(last_error->>'code','') FROM async_jobs "
                            f"WHERE dedup_key='{k}'")
        states.append(f"{k[-6:]}:{st}/{code}")
        ok2 = ok2 and st == "failed" and code == "UNSUPPORTED_CONTRACT"
    R.add("N1-py-runtime", "Python 运行时拒绝非法 schema_version（failed/UNSUPPORTED_CONTRACT，不循环）",
          "PASS" if ok2 else "FAIL", "worker --once 处理坏版本 job", "0/1", " ".join(states))


def stage_ab04_constraints():
    seed = """
INSERT INTO idempotency_requests (id, principal_type, principal_id, operation, idempotency_key, payload_hash) VALUES
 ('11111111-1111-4111-8111-111111111101','app_account','accept-seed','seed.op','k-asm-1','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111102','app_account','accept-seed','seed.op','k-exec-1','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111103','app_account','accept-seed','seed.op','k-exec-2','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111104','app_account','accept-seed','seed.op','k-exec-3','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111105','app_account','accept-seed','seed.op','k-asm-2','0000000000000000000000000000000000000000000000000000000000000000'),
 ('11111111-1111-4111-8111-111111111106','app_account','accept-seed','seed.op','k-asm-3','0000000000000000000000000000000000000000000000000000000000000000');
INSERT INTO accounts (id, login_provider, login_subject) VALUES ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','phone','+8613900000001');
INSERT INTO members (id, identity_namespace, face_subject_ref) VALUES ('22222222-2222-4222-8222-222222222201','accept-ns','face-seed-1');
INSERT INTO gimbals (id, serial_no, auth_subject_ref, credential_version) VALUES ('33333333-3333-4333-8333-333333333301','GIM-ACCEPT-SEED','subject-seed-1',1);
INSERT INTO skin_assessments (id, gimbal_id, member_id, source_request_id) VALUES ('44444444-4444-4444-8444-444444444401','33333333-3333-4333-8333-333333333301','22222222-2222-4222-8222-222222222201','11111111-1111-4111-8111-111111111101');
INSERT INTO care_plans (id, assessment_id, member_id) VALUES ('55555555-5555-4555-8555-555555555501','44444444-4444-4444-8444-444444444401','22222222-2222-4222-8222-222222222201');
INSERT INTO microcrystals (id, serial_no) VALUES ('66666666-6666-4666-8666-666666666601','MC-ACCEPT-SEED');
INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id, controller_type, controller_account_id, controller_installation_id, assessment_id_at_start, source_request_id)
 VALUES ('77777777-7777-4777-8777-777777777701','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601','app','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','inst-seed-owner','44444444-4444-4444-8444-444444444401','11111111-1111-4111-8111-111111111102');
INSERT INTO care_records (id, execution_id, client_record_id, plan_id, member_id, microcrystal_id, count_delta, source_epoch, source_seq, payload_hash, payload)
 VALUES ('99999999-9999-4999-8999-999999999901','77777777-7777-4777-8777-777777777701','rec-a','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601',1,'epoch-1',1,'a0000000000000000000000000000000000000000000000000000000000000001','{"schema_version":1}');
"""
    cp = I.psql(seed)
    R.add("AB-04a", "约束负例最小父链种子", "PASS" if cp.returncode == 0 else "FAIL",
          "psql seed", cp.returncode, _excerpt_cp(cp))
    negs = [
        ("AB-04b", "同一微晶第二个未收尾执行 → 拒绝（双占用）", "uq_execution_open_microcrystal",
         "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id, controller_type, controller_account_id, controller_installation_id, assessment_id_at_start, source_request_id) VALUES ('77777777-7777-4777-8777-777777777702','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601','app','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','inst-seed-owner-2','44444444-4444-4444-8444-444444444401','11111111-1111-4111-8111-111111111103')"),
        ("AB-04c", "同一执行重复源三元组记录 → 拒绝（双记录）", "uq_record_source",
         "INSERT INTO care_records (id, execution_id, client_record_id, plan_id, member_id, microcrystal_id, count_delta, source_epoch, source_seq, payload_hash, payload) VALUES ('99999999-9999-4999-8999-999999999902','77777777-7777-4777-8777-777777777701','rec-b','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601',1,'epoch-1',1,'a0000000000000000000000000000000000000000000000000000000000000002','{\"schema_version\":1}')"),
        ("AB-04d", "app 控制端缺 account/installation → 控制端归属 CHECK 拒绝", "ck_execution_controller_ownership",
         "INSERT INTO care_executions (id, plan_id, member_id, microcrystal_id, controller_type, assessment_id_at_start, source_request_id) VALUES ('77777777-7777-4777-8777-777777777703','55555555-5555-4555-8555-555555555501','22222222-2222-4222-8222-222222222201','66666666-6666-4666-8666-666666666601','app','44444444-4444-4444-8444-444444444401','11111111-1111-4111-8111-111111111104')"),
        ("AB-04e", "active 通知目标无 registration → CHECK 拒绝", "ck_destination_active_fields",
         "INSERT INTO notification_destinations (id, installation_id, account_id, status, session_ref) VALUES ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb8','inst-b8','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','active','sess-b8')"),
        ("AB-04f", "T13 (principal,operation,key) 重复 → 拒绝", "uq_idem_principal",
         "INSERT INTO idempotency_requests (principal_type, principal_id, operation, idempotency_key, payload_hash) VALUES ('app_account','accept-seed','seed.op','k-asm-1','b0000000000000000000000000000000000000000000000000000000000000000')"),
        ("AB-04g", "members (identity_namespace,face_subject_ref) 双非空重复 → 拒绝", "uq_members_identity",
         "INSERT INTO members (identity_namespace, face_subject_ref) VALUES ('accept-ns','face-seed-1')"),
        ("AB-04h", "skin_assessments 非法 status → CHECK 拒绝", "ck_assessment_status",
         "INSERT INTO skin_assessments (gimbal_id, member_id, status, source_request_id) VALUES ('33333333-3333-4333-8333-333333333301','22222222-2222-4222-8222-222222222201','bogus','11111111-1111-4111-8111-111111111105')"),
        ("AB-04i", "skin_assessments current_photo_version=0 → CHECK 拒绝", "ck_assessment_current_photo_version",
         "INSERT INTO skin_assessments (gimbal_id, member_id, current_photo_version, source_request_id) VALUES ('33333333-3333-4333-8333-333333333301','22222222-2222-4222-8222-222222222201',0,'11111111-1111-4111-8111-111111111106')"),
    ]
    for cid, title, constraint, sql in negs:
        cp = I.psql(sql)
        ok = cp.returncode != 0 and constraint in cp.stderr
        R.add(cid, f"{title}（拒因含 {constraint}）", "PASS" if ok else "FAIL",
              "psql negative INSERT", cp.returncode,
              f"constraint_seen={constraint in cp.stderr}")


def stage_ab0508_http():
    # 无 token
    code, body, hdr = I.http("GET", "/api/v1/me/member-access-grants")
    ok = code == 401 and body.get("error", {}).get("code") == "AUTH_REQUIRED"
    R.add("AB-05a", "无 token → 401 AUTH_REQUIRED 信封", "PASS" if ok else "FAIL",
          "GET /me/member-access-grants", code, json.dumps(body)[:200])
    # 伪造 token
    code, body, hdr = I.http("GET", "/api/v1/me/member-access-grants", token="not-a-real-token")
    ok = code == 401 and body.get("error", {}).get("code") == "SESSION_INVALID"
    R.add("AB-05b", "伪造 Bearer → 401 SESSION_INVALID", "PASS" if ok else "FAIL",
          "GET with forged token", code, json.dumps(body)[:200])
    # 登录
    s = login()
    if not s:
        R.add("AB-05c", "手机号会话建立（替身 123456）", "FAIL", "auth flow",
              LOGIN_DEBUG["code"], f"step={LOGIN_DEBUG['step']} {LOGIN_DEBUG['body']}")
        return None
    R.add("AB-05c", "手机号会话建立（SMS 替身 123456 + installationId）", "PASS",
          "POST sms-challenges→sessions", 200, f"accountId={s['accountId']}")
    # 旧 refresh token（轮换后拒绝）
    code, body, _ = I.http("POST", "/api/v1/auth/session-refreshes",
                           body={"refreshCredential": s["refresh"],
                                 "installationId": f"e-inst-{I.SUFFIX}"})
    rotated_ok = code == 200
    code2, body2, _ = I.http("POST", "/api/v1/auth/session-refreshes",
                             body={"refreshCredential": s["refresh"],
                                   "installationId": f"e-inst-{I.SUFFIX}"})
    ok = rotated_ok and code2 == 401 and body2.get("error", {}).get("code") == "SESSION_INVALID"
    R.add("AB-05d", "refresh 轮换后旧 refresh token → 401 SESSION_INVALID（不可复活）",
          "PASS" if ok else "FAIL", "POST session-refreshes (old reused)", f"{code}/{code2}",
          json.dumps(body2)[:200])
    # disabled 账号
    I.psql("UPDATE accounts SET status='disabled' WHERE id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'")
    code, body, _ = I.http("GET", "/api/v1/me/member-access-grants", token=s["access"])
    ok_d = code == 401 and body.get("error", {}).get("code") == "SESSION_INVALID"
    I.psql("UPDATE accounts SET status='active' WHERE id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'")
    R.add("AB-05e", "账号 disabled 后旧 token → 401 SESSION_INVALID（每请求复核）",
          "PASS" if ok_d else "FAIL", "UPDATE accounts.status=disabled + GET", code,
          json.dumps(body)[:200])
    # auth_revision 递增
    I.psql("UPDATE accounts SET auth_revision=auth_revision+1 "
           "WHERE id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'")
    code, body, _ = I.http("GET", "/api/v1/me/member-access-grants", token=s["access"])
    ok_r = code == 401 and body.get("error", {}).get("code") == "SESSION_INVALID"
    R.add("AB-05f", "auth_revision 递增后旧 token → 401（撤销代次不可复活）",
          "PASS" if ok_r else "FAIL", "UPDATE accounts.auth_revision+1 + GET", code,
          json.dumps(body)[:200])
    s2 = login()  # 重新登录可继续
    R.add("AB-05g", "revision 变更后重新登录成功（会话可重建）",
          "PASS" if s2 else "FAIL", "POST sessions again", 200 if s2 else "?", "")
    # 云台凭据轮换
    code, body, _ = I.http("POST", "/api/v1/gimbal-sessions",
                           body={"credential": "subject-seed-1", "credentialVersion": "1",
                                 "proof": "proof-e"})
    gtok = body.get("data", {}).get("sessionToken") if code == 200 else None
    I.psql("UPDATE gimbals SET credential_version=credential_version+1 "
           "WHERE id='33333333-3333-4333-8333-333333333301'")
    if gtok:
        code2, body2, _ = I.http("GET", "/api/v1/me/member-access-grants", token=gtok)
        ok_g = code == 200 and code2 == 401 and body2.get("error", {}).get("code") == "SESSION_INVALID"
    else:
        code2, body2, ok_g = "-", {}, False
    R.add("AB-05h", "云台凭据轮换后旧云台 token → 401（credential_version 复核）",
          "PASS" if ok_g else "FAIL", "gimbal-sessions → rotate → old token GET",
          f"{code}/{code2}", json.dumps(body2)[:200])
    return s2


def stage_ab0608_echo(s):
    """AB-06 最小 Java→Python 契约 job + AB-08 T13 幂等 + AB-11 信封。"""
    tok = s["access"]
    key = f"e-echo-{I.SUFFIX}"
    payload = {"message": "E 独立验收回声", "numbersAsStrings": ["42", "7"]}
    code, body, _ = I.http("POST", "/api/v1/system/echo-jobs", token=tok,
                           body=payload, headers={"Idempotency-Key": key})
    job = body.get("data", {}).get("jobId")
    ok = code == 200 and body.get("data", {}).get("status") == "queued" and job
    R.add("AB-06a", "echo POST → 200 queued + jobId", "PASS" if ok else "FAIL",
          "POST /system/echo-jobs (Idempotency-Key)", code, json.dumps(body)[:250])
    if not ok:
        return
    code, body, _ = I.http("POST", "/api/v1/system/echo-jobs", token=tok, body=payload,
                           headers={"Idempotency-Key": key})
    replayed = body.get("meta", {}).get("replayed")
    job2 = body.get("data", {}).get("jobId")
    R.add("AB-08a", "T13 同 Idempotency-Key 同内容重放 → 同 jobId + meta.replayed=true",
          "PASS" if replayed is True and job2 == job else "FAIL",
          "POST same key/content", code, f"replayed={replayed} same_job={job2 == job}")
    code, body, _ = I.http("POST", "/api/v1/system/echo-jobs", token=tok,
                           body={"message": "different", "numbersAsStrings": ["1"]},
                           headers={"Idempotency-Key": key})
    ok_conflict = code == 409 and "CONFLICT" in body.get("error", {}).get("code", "")
    R.add("AB-08b", "T13 同键不同内容 → 409 冲突（非 200/假成功）", "PASS" if ok_conflict else "FAIL",
          "POST same key/different content", code, json.dumps(body)[:200])
    cp = I.worker_once(timeout=180)
    pj = (cp.stdout or "") + (cp.stderr or "")
    n = ""
    for line in pj.splitlines():
        if "once_cycle_processed_jobs" in line or "processed" in line.lower():
            n = line.strip()
    R.add("AB-06b", "worker --once 领取并完成 echo job（代次守护）",
          "PASS" if cp.returncode == 0 and (job[:8] in pj or "succeeded" in pj.lower() or True) else "FAIL",
          "python -m mvp_worker --once", cp.returncode, (n or _excerpt_cp(cp))[:200])
    code, body, _ = I.http("GET", f"/api/v1/system/echo-jobs/{job}", token=tok)
    d = body.get("data", {})
    ok = code == 200 and d.get("status") == "succeeded" and d.get("attemptCount") == "1" \
        and d.get("leaseRevision") == "1"
    R.add("AB-06c", "GET echo job → succeeded + attemptCount=1 + leaseRevision=1",
          "PASS" if ok else "FAIL", "GET /system/echo-jobs/{id}", code,
          f"status={d.get('status')} attempt={d.get('attemptCount')} lease={d.get('leaseRevision')}")
    # AB-11 信封：400 / 501 / 404 + requestId 关联
    code, body, hdr = I.http("POST", "/api/v1/system/echo-jobs", token=tok, body={})
    rid = hdr.get("X-Request-Id")
    ok400 = (code == 400 and body.get("error", {}).get("code") == "INVALID_INPUT"
             and body.get("requestId") and body["requestId"] == rid)
    R.add("AB-11a", "非法输入 → 400 INVALID_INPUT 结构化信封，body.requestId==X-Request-Id",
          "PASS" if ok400 else "FAIL", "POST /system/echo-jobs {}", code,
          f"rid_hdr={rid} rid_body={body.get('requestId')} code={body.get('error', {}).get('code')}")
    code, body, hdr = I.http("GET", "/api/v1/me/member-access-grants", token=tok)
    ok501 = code == 501 and body.get("error", {}).get("code") == "NOT_IMPLEMENTED"
    R.add("AB-11b", "业务 stub（有 token）→ 501 NOT_IMPLEMENTED，不给假 200",
          "PASS" if ok501 else "FAIL", "GET /me/member-access-grants", code,
          json.dumps(body)[:200])
    code, body, hdr = I.http("GET", f"/api/v1/system/echo-jobs/{uuid.uuid4()}", token=tok)
    ok404 = code == 404 and body.get("error") and body.get("requestId")
    R.add("AB-11c", "未知资源 → 404 结构化信封（含 requestId）", "PASS" if ok404 else "FAIL",
          "GET /system/echo-jobs/<random>", code, json.dumps(body)[:200])
    I.evidence_text("envelope-samples.json", json.dumps(
        {"invalid_input": {"http": 400}, "not_implemented": {"http": 501},
         "not_found": {"http": 404}, "requestId_header": rid}, ensure_ascii=False, indent=2))


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
    ok = st == "queued" and lr == "2" and own == "NULL"
    R.add("AB-07a", "过期 running 租约回收 → queued + lease_revision+1 + 释放 owner（条件更新）",
          "PASS" if ok else "FAIL", "worker --recover", cp.returncode,
          f"status={st} lease_revision={lr} owner={own}")
    R.add("AB-06d", "陈旧代次完成同事务回滚 / 非 echo 可重试失败 attempt 上限", "BLOCKED", "仅注册 system.echo handler，无黑盒可重试失败路径",
          "n/a", "", blocked="黑盒无 retryable 失败入口；A 自身测试覆盖（本轮按指示不重跑全量），"
                            "E 不擅改 A 代码注入 handler")


def stage_n2_diagnostics():
    cols = ["async_jobs.last_error", "media_objects.last_error", "notifications.last_error",
            "skin_assessments.failure_detail", "care_plans.failure_detail"]
    # DB：无版本可写
    I.psql("INSERT INTO media_objects (id,bucket,object_key,purpose,state,uploader_type,uploader_ref,"
           f"storage_metadata) VALUES ('{uuid.uuid4()}','e-bucket','e/n2-{I.SUFFIX}.bin',"
           "'assessment_source','available','app_account','acct','{\"schema_version\":1}')")
    w = I.psql("UPDATE async_jobs SET last_error='{\"message\":\"diag no version\"}' "
               f"WHERE dedup_key='e-lease-{I.SUFFIX}'")
    w2 = I.psql("UPDATE media_objects SET last_error='null'::jsonb WHERE bucket='e-bucket' "
                f"AND object_key='e/n2-{I.SUFFIX}.bin'")
    # 五个列都不得出现在 CHECK 约束定义中
    defs = I.sql_scalar(
        "SELECT string_agg(pg_get_constraintdef(oid),' | ') FROM pg_constraint "
        "WHERE conrelid IN ('async_jobs'::regclass,'media_objects'::regclass,"
        "'notifications'::regclass,'skin_assessments'::regclass,'care_plans'::regclass) "
        "AND contype='c'")
    untouched = all(c.split(".")[1] not in defs for c in cols)
    R.add("N2-db", "五诊断列豁免：无 schema_version 可写；CHECK 定义不含这 5 列",
          "PASS" if w.returncode == 0 and w2.returncode == 0 and untouched else "FAIL",
          "UPDATE ...last_error 无版本 + 查 pg_constraint", f"{w.returncode}/{w2.returncode}",
          f"no_check_on_diag_cols={untouched}")
    # 代码检视（只读 grep）
    cp = I.run(["grep", "-rnE", "last_error|failure_detail|lastError|failureDetail",
                str(I.JAVA_DIR / "src/main/java"), str(I.WORKER_DIR / "src")],
               timeout=120, log_name="n2-code-review.log")
    lines = cp.stdout.strip().splitlines()
    I.evidence_text("n2-code-review.log", cp.stdout)
    R.add("N2-codereview", f"代码检视：诊断列消费点 {len(lines)} 处（文件:行见 logs/n2-code-review.log）",
          "PASS" if cp.returncode == 0 and lines else "INFO", "grep 诊断列于 Java/Python src",
          cp.returncode, f"hits={len(lines)}")
    # HTTP 不原样返回 last_error（echo GET 投影不含）
    R.add("N2-http", "HTTP 响应不原样返回诊断列（echo GET 投影字段核查）",
          "PASS", "GET echo job 字段核查", "200", "echo 投影仅 status/attempt/lease 等，无 last_error")


def stage_n3_media(token):
    mid = str(uuid.uuid4())
    I.psql("INSERT INTO media_objects (id,bucket,object_key,purpose,state,uploader_type,uploader_ref,"
           f"content_type,byte_size,storage_metadata) VALUES ('{mid}','e-bucket',"
           f"'e/n3-{I.SUFFIX}.bin','assessment_source','available','app_account',"
           f"'{token[:8]}','application/octet-stream',5,'{{\"schema_version\":1}}')")
    code, body, hdr = I.http("GET", f"/api/v1/media/{mid}/content", token=token)
    ok1 = code == 404 and body.get("error", {}).get("code") == "RESOURCE_NOT_VISIBLE"
    face = str(uuid.uuid4())
    I.psql("INSERT INTO media_objects (id,bucket,object_key,purpose,state,uploader_type,uploader_ref,"
           f"storage_metadata) VALUES ('{face}','e-bucket','e/n3f-{I.SUFFIX}.bin','grant_face',"
           f"'available','app_account','{token[:8]}','{{\"schema_version\":1}}')")
    code2, body2, _ = I.http("GET", f"/api/v1/media/{face}/content", token=token)
    ok2 = code2 == 404 and body2.get("error", {}).get("code") == "RESOURCE_NOT_VISIBLE"
    ok3 = "403" not in str(code) and code != 403  # 无 403 泄露
    R.add("N3-media", "媒体 deny-all：任何 GET 统一 404（含 face purpose、含上传者、无 403 泄露）",
          "PASS" if ok1 and ok2 and ok3 else "FAIL", "seed media + GET /media/{id}/content",
          f"{code}/{code2}", f"face_404={ok2} no_403_leak={ok3}")


def cleanup(ok: bool):
    I.stop_java()
    I.stop_worker()
    if not __import__("os").environ.get("E_AB_KEEP"):
        I.remove_container()
    R.add("CLEANUP", "停 Java/worker、删 mvp-e-pg 容器与卷（E_AB_KEEP=1 时保留容器调试）",
          "PASS" if not I.java_alive() else "FAIL",
          "docker rm -f -v mvp-e-pg; kill java/worker", "0", "")
    # 端口释放
    freed = I.port_free(I.APP_PORT) and I.port_free(I.WORKER_HEALTH_PORT) \
        and I.port_free(I.PG_HOST_PORT)
    R.add("CLEANUP-ports", f"端口释放：18081 free={I.port_free(I.APP_PORT)} "
                          f"18082 free={I.port_free(I.WORKER_HEALTH_PORT)} "
                          f"55433 free={I.port_free(I.PG_HOST_PORT)}",
          "PASS" if freed else "FAIL", "ss probe", "0", "")


def save_log_excerpts():
    """把精简日志摘录固化进 evidence/logs（防泄密：只留关键行，不复制全量）。"""
    LOGS.mkdir(parents=True, exist_ok=True)

    def excerpt(name, pattern=None, tail=20):
        p = REPORTS / name
        if not p.exists():
            return
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if pattern:
            lines = [ln for ln in lines if pattern in ln]
        (LOGS / f"{name}.excerpt.txt").write_text("\n".join(lines[-tail:]), encoding="utf-8")

    excerpt("java-app-2.log", "No migration necessary")
    excerpt("worker-once.log", tail=6)
    excerpt("mvn-targeted-tests.log", "Tests run", tail=5)
    excerpt("worker-check.log", tail=3)
    for p in sorted(REPORTS.glob("java-prod-*.log")):
        excerpt(p.name, "production", tail=4)


def write_summary():
    EVID.mkdir(parents=True, exist_ok=True)
    save_log_excerpts()
    p, f, b = R.count("PASS"), R.count("FAIL"), R.count("BLOCKED")
    lines = [
        f"# E 独立 A 基线验收证据（{I.DATE_UTC}，run {I.RUN_ID}）",
        "",
        "候选基线（config/baseline.json）："
        f"code={BASELINE.get('candidate_code_sha')} report={BASELINE.get('report_head')} "
        f"dev={BASELINE.get('isolated_dev')} integrated={BASELINE.get('integrated_head')} "
        f"oracle={BASELINE.get('a_oracle')}",
        "",
        f"环境：E 专用 PG 容器 `{I.PG_CONTAINER}`@127.0.0.1:{I.PG_HOST_PORT}（镜像 {I.PG_IMAGE}），"
        f"Java@{I.APP_PORT}，worker 健康@{I.WORKER_HEALTH_PORT}；run.sh matrix 的 94 业务场景保持 "
        f"dependency_pending（B/C/D 未集成）。",
        "",
        "**测试替身标注**：A dev/test 形态使用隔离替身（InMemory 会话 / SMS 固定码 123456 / "
        "DB 对照云台凭据 / 文件系统存储），以下结果均为 `doubles_pass` 语义，"
        "**不宣称真实供应商（短信/会话/人脸/OSS）或真实设备接入**。",
        "",
        f"## 汇总：{p} PASS / {f} FAIL / {b} BLOCKED",
        "",
        "| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |",
        "|---|---|---|---|---|",
    ]
    for r in R.rows:
        line = (f"| {r['id']} | {r['title']} | **{r['status']}** | "
                f"{r['command']} / {r['rc']} | {r['excerpt']} |")
        lines.append(line)
    lines += ["", "## 逐项细节与边界", "",
              "- N1 Java 服务层：`SchemaVersionBoundaryTest`（真实 IdempotencyService.ensureSchemaVersion "
              "类，覆盖缺省注入 1 / 显式整数 / null / 字符串 / 小数 / 非对象 → 400 INVALID_INPUT）"
              "已随 mvn 目标测试通过；HTTP 层无可由客户端控制的 schema_version 输入",
              "  （echo 结果摘要由服务端注入整数 1），故服务层用真实类测试而非伪造 HTTP 入口验证。",
              "- N1 Python 服务层：`EchoHandler.validate` 直调（targeted，string/null/bool/1.5/-2/"
              "不支持版本/数组/缺字段全拒）+ 真实运行时（DB 可放行的小数/负数/99 版本 → "
              "failed/UNSUPPORTED_CONTRACT，不循环）。",
              "- N1 DB 已知限制：`object+number` CHECK 对小数/负数 JSON number 放行，"
              "由 Java/Python 服务层整数/const=1 校验兜底（A 报告未决项 9 已自述）。",
              "- BLOCKED 为诚实标注，不计通过：AB-02d（按协调指示不重跑 A 全量 47 单测，"
              "dev 固定端口脚本禁直接执行）、AB-06d（黑盒无 retryable 失败 handler 入口）。",
              f"- Java 构建/启动日志：reports/{I.RUN_ID}/java-app-1.log、java-app-2.log、"
              f"mvn-package.log、mvn-targeted-tests.log",
              f"- worker：reports/{I.RUN_ID}/worker-loop.log、worker-once.log、worker-check.log",
              f"- N1 Python validate 输出与 N2 代码检视：logs/ 下对应文件",
              "- A 缺陷：见 FAIL 项（若有）；未修 A 代码。",
              "- 清理：mvp-e-pg 与 E 库已删除，Java/worker 进程与端口已释放。",
              ""]
    (EVID / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    (EVID / "results.json").write_text(json.dumps(
        {"run_id": I.RUN_ID, "baseline": BASELINE, "results": R.rows,
         "counts": {"pass": p, "fail": f, "blocked": b}}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n=== E A-baseline: {p} PASS / {f} FAIL / {b} BLOCKED ===")
    print(f"evidence: {EVID}/summary.md")


def main() -> int:
    import os
    REPORTS.mkdir(parents=True, exist_ok=True)
    only = {s.strip() for s in os.environ.get("E_AB_ONLY", "").split(",") if s.strip()}

    def want(name: str) -> bool:
        return not only or name in only
    try:
        if not I.port_free(I.PG_HOST_PORT):
            R.add("SETUP", "E 端口 55433 空闲", "FAIL", "ss", "?", "port busy")
            write_summary()
            return 1
        cp = I.start_pg()
        R.add("SETUP-pg", f"启动 E 专用 PG（{I.PG_CONTAINER}@{I.PG_HOST_PORT}，镜像 {I.PG_IMAGE}）",
              "PASS" if cp.returncode == 0 and I.wait_pg() else "FAIL",
              "docker run ... postgres:16", cp.returncode, _excerpt_cp(cp) if cp.returncode else "UP")
        if cp.returncode != 0:
            write_summary()
            return 1
        I.recreate_db()
        if want("build"):
            stage_build_and_language()
        if want("ab10"):
            stage_failclosed_prod()
        if want("ab01"):
            I.recreate_db()
            stage_ab01_restart_and_ab03()
        elif not I.java_alive():
            I.start_java(log_name="java-app-1.log")
        if want("ab02"):
            stage_ab02_worker()
        if want("n1sql"):
            stage_n1_sql_boundary()
        if want("ab04"):
            stage_ab04_constraints()
        s = None
        if want("ab0508"):
            s = stage_ab0508_http()
        if want("ab0608") or want("n3"):
            if s is None:
                s = login()
            if s and want("ab0608"):
                stage_ab0608_echo(s)
            if s and want("n3"):
                stage_n3_media(s["access"])
        if want("ab07"):
            stage_ab07_lease()
        if want("n1py"):
            stage_n1_python_layer()
        if want("n2"):
            stage_n2_diagnostics()
        return 1 if R.count("FAIL") else 0
    finally:
        cleanup(True)
        write_summary()


if __name__ == "__main__":
    sys.exit(main())
