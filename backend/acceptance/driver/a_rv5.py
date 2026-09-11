#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E 对 A 561c338（RV-5 裁定实现）的**有界复验**：RV5-1..RV5-8 + CLEANUP。

独立证据目录 evidence/A-rv5-2026-09-10-561c338/<RUN_ID>/；不覆盖既有证据目录。
结论仅"RV-5 有界复验（PARTIAL）结果：通过（附条件）/未通过" + 组合意见声明。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from driver import a_baseline as AB  # noqa: E402
from driver import a_reverify as AR  # noqa: E402
from driver import infra as I  # noqa: E402
from driver import verify_reverify_sentinel as verify_sentinel  # noqa: E402
from driver.infra import R, REPORTS  # noqa: E402

EXPECTED_RV5 = verify_sentinel.EXPECTED_RV5
A_CODE = "561c338137aaa1da7c8e00969da3c5381207b194"
A_CAND = {"code": A_CODE, "report": "5ae53b6", "dev": "9b3e4a1",
          "integrated": "e1d54b92e8b6b20a1e1b5631cc17be95b8d5e2a1"}
ENUM = AR.REASON_ENUM
VALIDATE = AR.VALIDATE
EVID_DIRNAME = "A-rv5-2026-09-10-561c338"
STRICT_BODIES: list = []  # 仅 200 成功投影（走严格 schema 的捕获体）


def _add(cid, title, status, command="", rc="", excerpt="", blocked=""):
    R.add(cid, title, status, command, rc, excerpt, doubles="doubles_pass", blocked=blocked)


def post_echo(token, key=None, job_id=None, message="rv5"):
    headers = {"Idempotency-Key": key} if key else {}
    body = {"message": message, "numbersAsStrings": ["1"]}
    if job_id:
        body["jobId"] = job_id
    return I.http("POST", "/api/v1/system/echo-jobs", token=token, body=body, headers=headers)


def err_subtree(body):
    return json.dumps((body or {}).get("error") or {}, sort_keys=True, ensure_ascii=False)


def canon_public(body):
    """完整公开响应规范化：仅递归排除逐请求字段 requestId，其余全部保留后逐字节比较。"""
    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k != "requestId"}
        if isinstance(o, list):
            return [strip(x) for x in o]
        return o
    return json.dumps(strip(body), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def forbidden_hit(text, needles):
    low = text.lower()
    return [n for n in needles if n and n.lower() in low]


def three_state_ok(canon_bodies, forbidden, seed_ok, codes_ok):
    """三态 404 判定（纯函数，负例可单测）：种子必须成功+完整公开体等值+无禁止内容+code 一致。"""
    if not seed_ok:
        return False
    if len(set(canon_bodies)) != 1:
        return False
    if forbidden:
        return False
    return bool(codes_ok)


def post_collision_ok(canon_set, forbidden, t13_first, t13_after_replay,
                      a_row_unchanged, b_rows_zero, positive_ok):
    """POST 碰撞判定（纯函数）：完整拒绝体等值 + T13 首/重放均 rejected + 行不变 + 无 B 行 + 正例。"""
    return (len(set(canon_set)) == 1 and not forbidden
            and t13_first == "rejected|RESOURCE_NOT_VISIBLE"
            and t13_after_replay == "rejected|RESOURCE_NOT_VISIBLE"
            and a_row_unchanged and b_rows_zero == "0" and positive_ok)


def snapshot(job_id):
    """目标行完整持久化行快照（SELECT *）。返回 (ok, json_text)。"""
    cp = I.psql("SELECT row_to_json(t)::text FROM (SELECT * FROM async_jobs "
                f"WHERE id='{job_id}') t")
    txt = (cp.stdout or "").strip()
    return (cp.returncode == 0 and bool(txt)), txt


def t13_row(principal_id, key):
    return I.sql_scalar(
        "SELECT status || '|' || coalesce(result_summary->>'code','') FROM idempotency_requests"
        f" WHERE principal_id='{principal_id}' AND idempotency_key='{key}'"
        " AND operation='system.echo.create'")


def rv5_conclusion(settle):
    c = settle["counts"]
    if settle.get("unknown_status"):
        return f"**RV-5 有界复验（PARTIAL）结果：拒绝**——未知状态 {settle['unknown_status']}。"
    if c["fail"] > 0 or c["blocked"] > 0:
        return (f"**RV-5 有界复验（PARTIAL）结果：未通过**——{c['fail']} FAIL / {c['blocked']} BLOCKED。"
                "组合意见：本次有限验证 + 历史适用证据，整体验收意见由总协调形成。")
    if not AB.settlement_complete(settle):
        return ("**RV-5 有界复验（PARTIAL）结果：未通过**——结算不完整；"
                "组合意见：本次有限验证 + 历史适用证据，整体验收意见由总协调形成。")
    tail = ("组合意见：本次有限验证 + 历史适用证据（A-baseline 26d97fb / A-reverify f6e500e），"
            "整体验收意见由总协调形成；本报告不输出全量通过或 A 基础验收结论。")
    if c["info"] > 0:
        ids = [r["id"] for r in R.rows if r["status"] == "INFO"]
        return (f"**RV-5 有界复验（PARTIAL）结果：通过（附条件）**——{c['pass']} PASS / "
                f"{c['info']} INFO 待裁定（{ids}）。{tail}")
    return f"**RV-5 有界复验（PARTIAL）结果：通过**——{c['pass']} PASS / 0 FAIL / 0 BLOCKED。{tail}"


# ---------------- RV5-1 ----------------

def rv5_1_build():
    diff = I.run(["git", "diff", A_CODE, "--", "backend/web-java", "backend/worker-python",
                  "backend/contracts"], cwd=I.REPO, timeout=120, log_name="rv5-1-git-diff.log")
    head = I.run(["git", "rev-parse", "HEAD"], cwd=I.REPO, timeout=60).stdout.strip()
    diff_empty = diff.returncode == 0 and not diff.stdout.strip()
    cp = I.run(["mvn", "-B", "-q", "-DskipTests", "package"], cwd=I.JAVA_DIR, timeout=1800,
               log_name="rv5-1-mvn-package.log")
    jar = I.java_jar()
    jar_sha = hashlib.sha256(jar.read_bytes()).hexdigest()[:16] if jar.exists() else "-"
    up = I.start_java(log_name="rv5-1-java-app.log") if cp.returncode == 0 else False
    ok = diff_empty and cp.returncode == 0 and up
    _add("RV5-1", "从当前源码重建：A 源码==561c338（git diff 空）+ mvn 重建 jar + 启动健康；未用镜像",
         "PASS" if ok else "FAIL",
         "git diff 561c338 -- web-java worker-python contracts; mvn -DskipTests package; java -jar",
         cp.returncode, f"diff_empty={diff_empty} HEAD={head[:12]} jar={jar.name} "
                        f"sha256[:16]={jar_sha} health_up={up}；"
                        "同源各自重建，jar 哈希可能因构建元数据不同而非字节一致")


# ---------------- RV5-2 ----------------

def rv5_2_get_creator(s):
    job = post_echo(s["access"])[1].get("data", {}).get("jobId", "")
    code, body, _ = I.http("GET", f"/api/v1/system/echo-jobs/{job}", token=s["access"])
    v, why = AR.proj_verdict(code, job, body)
    AR._capture(body, "rv5-2-creator")
    STRICT_BODIES.append(body)
    marker = "Bearer RV5_DIAG_SECRET_MARKER_98765"
    sql = ("WITH u AS (UPDATE async_jobs SET last_error=jsonb_build_object('code',"
           f"'RV5_DIAG','message','{marker}','retryable',true) WHERE id='{job}' RETURNING id) "
           "SELECT count(*) FROM u")
    cp = I.psql(sql)
    code2, body2, _ = I.http("GET", f"/api/v1/system/echo-jobs/{job}", token=s["access"])
    v2, why2 = AR.proj_verdict(code2, job, body2, forbid=(marker, "RV5_DIAG"))
    STRICT_BODIES.append(body)
    STRICT_BODIES.append(body2)
    ok = (bool(job) and v is True and cp.returncode == 0 and cp.stdout.strip() == "1"
          and v2 is True)
    _add("RV5-2", "GET 创建者可见 + 泄漏点抽查回归：jobId 关联 + 投影仅 closed enum，"
                  "合成 marker/原始 code 缺席",
         "PASS" if ok else "FAIL", "POST echo → 创建者 GET（jobId 断言）+ SQL marker → GET",
         f"{code}/{code2}", f"creator={why} | marker_seed_rows={cp.stdout.strip()} | {why2}")


# ---------------- RV5-3 ----------------

def rv5_3_three_state_404(s):
    j1 = post_echo(s["access"])[1].get("data", {}).get("jobId", "")
    s2 = AB.login(identity_tag=uuid.uuid4().hex[:8])
    accounts_differ = bool(s2) and s2["accountId"] != s["accountId"]
    s1_valid = I.http("GET", f"/api/v1/system/echo-jobs/{j1}", token=s["access"])[0] == 200
    j2 = post_echo(s2["access"])[1].get("data", {}).get("jobId", "") if s2 else ""
    s2_valid = bool(s2) and I.http("GET", f"/api/v1/system/echo-jobs/{j2}",
                                   token=s2["access"])[0] == 200
    foreign = I.http("GET", f"/api/v1/system/echo-jobs/{j1}", token=s2["access"] if s2 else "")
    missing = I.http("GET", f"/api/v1/system/echo-jobs/{uuid.uuid4()}", token=s["access"])
    # 非 echo 种子：INSERT RETURNING rowcount==1 + 回查（失败则该项 BLOCKED，绝不 PASS）
    ne = str(uuid.uuid4())
    cp = I.psql("WITH ins AS (INSERT INTO async_jobs (id,job_type,dedup_key,owner_type,owner_id,"
                f"payload,status) VALUES ('{ne}','rv5.non-echo','rv5-ne-{ne}','app_account',"
                f"'{s['accountId']}',jsonb_build_object('schema_version',1),'queued') RETURNING id) "
                "SELECT count(*) FROM ins")
    seed_rows = (cp.stdout or "").strip()
    back = I.sql_scalar("SELECT id::text||'|'||job_type||'|'||owner_id::text FROM async_jobs "
                        f"WHERE id='{ne}'")
    seed_ok = cp.returncode == 0 and seed_rows == "1" \
        and back == f"{ne}|rv5.non-echo|{s['accountId']}"
    non_echo = I.http("GET", f"/api/v1/system/echo-jobs/{ne}", token=s["access"])
    bodies = (foreign[1], missing[1], non_echo[1])
    canon = [canon_public(b) for b in bodies]
    raw_all = " ".join(json.dumps(b, ensure_ascii=False) for b in bodies)
    needles = [j1, s["accountId"], (s2 or {}).get("accountId", ""), "app_account",
               "system.echo", "rv5.non-echo", "schema_version"]
    hit = forbidden_hit(raw_all, needles)
    codes_ok = all((b.get("error") or {}).get("code") == "RESOURCE_NOT_VISIBLE" for b in bodies)
    statuses_ok = foreign[0] == 404 and missing[0] == 404 and non_echo[0] == 404
    ok = (accounts_differ and s1_valid and s2_valid and statuses_ok
          and three_state_ok(canon, hit, seed_ok, codes_ok))
    status = "PASS" if ok else ("BLOCKED" if not seed_ok else "FAIL")
    detail = (f"accounts_differ={accounts_differ} s1_valid={s1_valid} s2_valid={s2_valid} "
              f"status={foreign[0]}/{missing[0]}/{non_echo[0]} "
              f"public_body_equal={len(set(canon)) == 1} forbidden_hit={hit} "
              f"seed_ok={seed_ok}(rows={seed_rows}) back={back} codes_ok={codes_ok}")
    _add("RV5-3", "GET 三态统一 404 不可区分：外来/不存在/非 echo——完整公开响应（仅排除 "
                  "requestId）规范化等值 + 全态无归属/类型/payload 泄露 + 种子回查",
         status, "三态 GET + 完整 body 规范化逐字节比较 + INSERT RETURNING 回查",
         f"{foreign[0]}/{missing[0]}/{non_echo[0]}", detail)


# ---------------- RV5-4 ----------------

def rv5_4_unauth():
    code, body, _ = I.http("GET", f"/api/v1/system/echo-jobs/{uuid.uuid4()}")
    e = body.get("error") or {}
    ok1 = code == 401 and e.get("code") == "AUTH_REQUIRED" and bool(body.get("requestId"))
    code2, body2, _ = I.http("GET", f"/api/v1/system/echo-jobs/{uuid.uuid4()}",
                             token="forged-not-a-token")
    e2 = body2.get("error") or {}
    ok2 = code2 == 401 and e2.get("code") == "SESSION_INVALID"
    _add("RV5-4", "未认证/伪造凭据 → 401（基本错误信封检查，非严格 schema）",
         "PASS" if ok1 and ok2 else "FAIL", "GET echo job 无 token/伪造 token",
         f"{code}/{code2}", f"no-token={code}/{e.get('code')} forged={code2}/{e2.get('code')}")


# ---------------- RV5-5 ----------------

def rv5_5_post_collision(s):
    a, detail = s, []
    b = AB.login(identity_tag=uuid.uuid4().hex[:8])
    if not b:
        _add("RV5-5", "POST dedup 碰撞矩阵", "FAIL", "login second account", "?", "B login failed")
        return
    # 并发窗口保证：本项不启动 worker，碰撞序列期间无 worker 并发修改目标行
    worker_running = I.WORKER_PROC is not None
    explicit = str(uuid.uuid4())
    key_a = f"rv5-ka-{uuid.uuid4()}"
    key_b = f"rv5-kb-{uuid.uuid4()}"
    code_a, body_a, _ = post_echo(a["access"], key_a, explicit)
    job_a = body_a.get("data", {}).get("jobId", "")
    ok_before, before = snapshot(job_a)
    b_principal = f"{b['accountId']}:{b['installationId']}"
    # ① B 无键碰撞
    code1, body1, _ = post_echo(b["access"], None, explicit)
    denied_get = I.http("GET", f"/api/v1/system/echo-jobs/{uuid.uuid4()}", token=b["access"])
    # ② keyed#1
    code2, body2, _ = post_echo(b["access"], key_b, explicit)
    t13 = t13_row(b_principal, key_b)
    # ③ keyed#2 重放
    code3, body3, _ = post_echo(b["access"], key_b, explicit)
    t13_after = t13_row(b_principal, key_b)
    # ④ 原 A 行完整快照（SELECT *）前后一致
    ok_after, after = snapshot(job_a)
    a_row_unchanged = ok_before and ok_after and bool(before) and before == after
    # ⑤ B 属行=0
    b_rows = I.sql_scalar("SELECT count(*) FROM async_jobs WHERE owner_type='app_account' "
                          f"AND owner_id='{b['accountId']}'")
    # ⑥ 正例：同主体同键重放 → 同 jobId + replayed
    code6, body6, _ = post_echo(a["access"], key_a, explicit)
    positive_ok = (code6 == 200 and body6.get("data", {}).get("jobId") == job_a
                   and body6.get("meta", {}).get("replayed") is True)
    # 统一完整拒绝体比较：无键/keyed#1/重放/规范 GET 拒绝（仅排除 requestId）
    canon = [canon_public(x) for x in (body1, body2, body3, denied_get[1])]
    raw_all = " ".join(json.dumps(x, ensure_ascii=False) for x in (body1, body2, body3))
    hit = forbidden_hit(raw_all, [job_a, explicit, "app_account", "system.echo", "payload"])
    statuses_ok = code1 == 404 and code2 == 404 and code3 == 404
    ok = (code_a == 200 and bool(job_a) and statuses_ok
          and post_collision_ok(canon, hit, t13, t13_after, a_row_unchanged, b_rows, positive_ok))
    status = "PASS" if ok else ("BLOCKED" if not (ok_before and ok_after) else "FAIL")
    detail = (f"worker_running_during_window={worker_running}（本项不启 worker，无并发修改） | "
              f"no-key: {code1}/{(body1.get('error') or {}).get('code')} | "
              f"keyed#1: {code2} t13={t13} | keyed#2: {code3} t13_replay={t13_after} | "
              f"deny_body_equal={len(set(canon)) == 1} forbidden_hit={hit} | "
              f"A_row_full_snapshot_unchanged={a_row_unchanged} B_owned_rows={b_rows} | "
              f"positive_replay: {code6} same_job={body6.get('data', {}).get('jobId') == job_a}")
    _add("RV5-5", "POST dedup 碰撞矩阵（①无键 404 ②keyed 404+T13 rejected ③重放同一拒绝+T13 复验 "
                  "④SELECT * 全字段行不变 ⑤无 B 属行 ⑥同主体正例）：统一完整拒绝体等值+防投影",
         status, "A 显式 body.jobId 建 job → B 同 jobId 无键/keyed 碰撞/重放 + SQL 查证",
         f"{code1}/{code2}/{code3}/{code6}", detail)


# ---------------- RV5-6 ----------------

def rv5_6_contracts(caps):
    st = I.run([str(I.PY), str(VALIDATE), "--selftest"], cwd=I.CONTRACTS, timeout=180,
               log_name="rv5-6-selftest.log")
    selftest_ok = st.returncode == 0 and "10 checks passed" in st.stdout
    samp = I.run([str(I.PY), "scripts/validate_samples.py"], cwd=I.CONTRACTS, timeout=180,
                 log_name="rv5-6-samples.log")
    nchecks_m = re.search(r"(\d+)\s+checks", samp.stdout)
    nchecks = nchecks_m.group(1) if nchecks_m else "?"
    samples_ok = samp.returncode == 0 and nchecks == "50"
    oas = I.run([str(I.PY), "-c", "import yaml\nfrom openapi_spec_validator import validate\n"
                 "validate(yaml.safe_load(open('openapi/openapi.yaml')))\nprint('OPENAPI VALID')"],
                cwd=I.CONTRACTS, timeout=180, log_name="rv5-6-openapi.log")
    oas_ok = oas.returncode == 0 and "OPENAPI VALID" in oas.stdout
    # 成功投影（echo-job-view 200）严格校验；404/401 仅基本信封（OAS 严格机制只解析 echo-view 200）
    paths = [AR._capture(b, f"rv5-6-{i}") for i, b in enumerate(caps) if isinstance(b, dict)]
    ok_strict, why_strict = AR._strict_validate(paths, "rv5-captured") if paths else (False, "no caps")
    ok = selftest_ok and samples_ok and oas_ok and ok_strict
    _add("RV5-6", "有界严格响应契约：成功投影走严格 schema（validate_responses）+ selftest 10/10 + "
                  "samples 50 + OpenAPI；404/401 仅基本信封检查（如实分类）",
         "PASS" if ok else "FAIL",
         "validate_responses <200 捕获>; --selftest; validate_samples; openapi_spec_validator",
         "0/1", f"selftest={selftest_ok} samples={samples_ok}({nchecks}) oas={oas_ok} "
                f"captured_200_strict={ok_strict} | 404/401=基本信封检查: {why_strict[:80]}")


# ---------------- RV5-7/8 ----------------

def rv5_7_limit_disclosure():
    dn = (I.CONTRACTS / "decisions-notes.md").read_text(encoding="utf-8")
    amd = (I.REPO / "backend/handoffs/A.md").read_text(encoding="utf-8")
    dn_ok = ("显式 body jobId 的全局 dedup 边界" in dn) \
        and ("不泄露该行 id/status/归属/类型" in dn)
    a_ok = "availability-oracle" in amd
    ok = dn_ok and a_ok
    I.evidence_text("rv5-7-disclosure-check.txt",
                    f"decisions_notes_§11_dedup_boundary={dn_ok}\n"
                    f"A_md_availability_oracle={a_ok}\n")
    _add("RV5-7", "已接受限制披露：全局 dedup availability-oracle（碰撞 404 vs 新键 200 仅揭示 "
                  "dedup 键不可用；完整 POST 存在性不可区分=单独决策，A 未决项 11）",
         "PASS" if ok else "INFO", "读 decisions-notes.md §11 + A.md 核对该披露",
         "0" if ok else "1", f"decisions_dedup_boundary={dn_ok} A_md_availability_oracle={a_ok}")


def rv5_8_history_ledger():
    base = I.ROOT / "evidence"
    dirs = {"A-baseline-2026-09-10": (base / "A-baseline-2026-09-10").exists(),
            "A-reverify-2026-09-10": (base / "A-reverify-2026-09-10").exists()}
    diff = I.run(["git", "diff", "--name-only", "f6e500e", A_CODE], cwd=I.REPO, timeout=120,
                 log_name="rv5-8-diff.log")
    files = [ln for ln in diff.stdout.splitlines() if ln.strip()]
    consumption = [f for f in files if any(k in f for k in
                   ("MediaService.java", "MediaIntakeService.java", "expire.py",
                    "media/repository.py"))]
    ok = all(dirs.values()) and not consumption
    _add("RV5-8", "历史证据台账+SHA 适用范围：既有基础/定向证据存在；f6e500e..561c338 未改 "
                  "9 处消费点文件 → f6e500e 复核台账仍适用（组合意见=本次有限验证+历史证据）",
         "PASS" if ok else "FAIL", "检查证据目录存在 + git diff --name-only f6e500e 561c338",
         diff.returncode, f"dirs={dirs} changed_files={len(files)} consumption_point_files={consumption}")


def write_outputs_rv5(settle, rc, formal_dir):
    counts = settle["counts"]
    result = {"schema": "e-acceptance-a-rv5/1", "run_id": I.RUN_ID, "mode": "rv5-reverify",
              "scope": "PARTIAL (RV5-1..RV5-8)", "a_candidate": A_CAND,
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
    lines = [
        f"# E RV-5 有界复验（PARTIAL）——A {A_CODE[:12]}，run {I.RUN_ID}",
        "",
        "> **RV-5 有界复验（PARTIAL），非新 SHA 全量验收**：只复验 RV-5 裁定（echo 归属 + "
        "GET/POST 统一 404 + dedup 碰撞）；历史适用证据见 RV5-8 台账。",
        "",
        f"新 A 候选：code={A_CAND['code']} report={A_CAND['report']} dev={A_CAND['dev']} "
        f"integrated={A_CAND['integrated']}",
        "",
        f"## 结算：{settle['settled']}/{settle['expected']} 唯一结算；"
        f"{counts['pass']} PASS / {counts['fail']} FAIL / {counts['blocked']} BLOCKED / "
        f"{counts['info']} INFO（计数和={sum(counts.values())}==行数 {settle.get('rows')}）；"
        f"final_exit={rc}",
        "",
        rv5_conclusion(settle),
        "",
        "| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |",
        "|---|---|---|---|---|",
    ]
    for r in R.rows:
        cell = (lambda s: str(s).replace("|", "/").replace("\n", " "))
        lines.append(f"| {r['id']} | {cell(r['title'])} | **{r['status']}** | "
                     f"{cell(r['command'])} / {r['rc']} | {cell(r['excerpt'])} |")
    lines += [
        "", "## 严格 vs 基本校验分类",
        "- 严格 schema：echo-job-view 200 成功投影（validate_responses 机制）。",
        "- 基本错误信封检查（非严格 schema）：404/401/keyed 拒绝重放——OAS 严格机制当前只解析 "
        "echo-view 200 路径。",
        "", "## 组合意见边界",
        "本次为 RV-5 限定的有界验证；整体验收意见=本次有限验证 + 历史适用证据"
        "（A-baseline-2026-09-10=26d97fb；A-reverify-2026-09-10=f6e500e），由总协调形成；"
        "本报告不输出全量通过或 A 基础验收结论。",
        "", "## A 缺陷清单", "",
    ]
    fails = [r for r in R.rows if r["status"] == "FAIL"]
    lines.append("（无 FAIL 项）" if not fails else "")
    for r in fails:
        lines.append(f"- **{r['id']}** {r['title']}；{r['excerpt']}")
    lines += ["", "## 附件", "- `logs/rv5-*.log`、`logs/responses/`、`logs/rv5-5-*.log`", ""]
    (formal_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n=== E A-rv5: {counts['pass']} PASS / {counts['fail']} FAIL / "
          f"{counts['blocked']} BLOCKED / {counts['info']} INFO "
          f"(settled {settle['settled']}/{settle['expected']}, exit={rc}) ===")
    print(rv5_conclusion(settle))
    print(f"evidence: {formal_dir}/summary.md")


def main() -> int:
    formal_dir = I.ROOT / "evidence" / EVID_DIRNAME / I.RUN_ID
    I.set_output_mode(True, formal_dir=formal_dir)
    REPORTS.mkdir(parents=True, exist_ok=True)
    ok_lock, why = I.acquire_single_instance_lock()
    if not ok_lock:
        print(f"[FATAL] {why}")
        return 4
    try:
        if not all(I.check_ports().values()) or I.container_exists():
            _add("RV5-0", "前置：端口空闲且无同名容器", "FAIL", "ss/docker", "1", "环境未净")
        else:
            cp = I.start_pg()
            if cp.returncode != 0 or not I.wait_pg():
                _add("RV5-0", "启动 E 专用 PG", "FAIL", "docker run mvp-e-pg", cp.returncode, "")
            else:
                I.recreate_db()
                rv5_1_build()
                s = AB.login()
                if s:
                    rv5_2_get_creator(s)
                    rv5_3_three_state_404(s)
                    rv5_4_unauth()
                    rv5_5_post_collision(s)
                else:
                    _add("RV5-2", "创建者会话建立", "FAIL", "login", "?", "login failed")
                rv5_6_contracts(STRICT_BODIES)
                rv5_7_limit_disclosure()
                rv5_8_history_ledger()
    finally:
        try:
            I.stop_java()
            I.stop_worker()
            try:
                I.remove_container()
            except Exception as exc:
                _add("CLEANUP", "按 run 标签清理 E 容器", "FAIL", "docker rm", "1", str(exc))
            if "CLEANUP" not in {r["id"] for r in R.rows}:
                _add("CLEANUP", "停进程并按 run 标签删除 mvp-e-pg",
                     "PASS" if not I.container_exists() else "FAIL", "docker rm -f -v", "0", "")
            freed = I.port_free(I.APP_PORT) and I.port_free(I.WORKER_HEALTH_PORT) \
                and I.port_free(I.PG_HOST_PORT)
            _add("CLEANUP-ports", "端口释放", "PASS" if freed else "FAIL", "ss", "0", "")
        finally:
            I.release_single_instance_lock()
        settle = AB.settlement(expected=EXPECTED_RV5)
        rc = AB.final_exit(True, settle)
        write_outputs_rv5(settle, rc, formal_dir)
        verify_sentinel.write_sentinel(I.RUN_ID, settle, rc, mode="rv5-reverify",
                                       expected=EXPECTED_RV5)
    return rc


if __name__ == "__main__":
    sys.exit(main())
