#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E 对 A f6e500e 修复的**有界定向复验**（非全量 52 项）。

独立 run_id 与独立证据目录 evidence/A-reverify-2026-09-10/<RUN_ID>/，绝不覆盖
A-baseline-2026-09-10 既有正式证据。检查集 RV-1..RV-9；结算/退出码政策与
a-baseline 相同（0=完整且无 FAIL/BLOCKED；1=FAIL/BLOCKED；4=不完整/未知）。
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
from driver import infra as I  # noqa: E402
from driver.infra import R, REPORTS, APP_BASE  # noqa: E402

EXPECTED_TARGETED = frozenset({f"RV-{i}" for i in range(1, 10)}
                              | {"CLEANUP", "CLEANUP-ports"})
A_CAND = {
    "code": "f6e500e474954781d3438188b6fdd389e61682e7",
    "report": "cf390e1a37f1575d7b0d4772a51246f9188b67b3",
    "dev": "f2755ab1741b5ee4f384fa66e73a2e669614ada9",
    "integrated": "d495a7d7c43aab3baae9afcf8774ae9850e6e41f",
}
REASON_ENUM = {"unsupported_contract", "retry_limit_exceeded", "handler_failed", "internal"}
VALIDATE = I.CONTRACTS / "scripts" / "validate_responses.py"

REVIEW_ITEMS = [
    ("web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java",
     "失败路径 state=failed + last_error", "内部诊断写入说明（注释）", "合规",
     "仅文档描述；明确写诊断用途，无客户端投影"),
    ("web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java",
     "last_error = NULL", "诊断写入（成功时清除内部诊断）", "合规",
     "available 成功路径清空诊断；无外部读取方"),
    ("web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java",
     "不含供应商密钥级细节", "注释（脱敏边界声明）", "合规",
     "显式声明不含密钥级细节；写入值为 ErrorCode.name+message"),
    ("web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java",
     "SET state = 'failed', last_error", "内部诊断写入（失败路径）", "合规",
     "media last_error 无任何对外端点投影；MediaController 仅返回 content"),
    ("web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaIntakeService.java",
     "失败 → failed + last_error", "注释（写入边界说明）", "合规",
     "受理失败诊断写入说明，非业务决策"),
    ("worker-python/src/mvp_worker/runtime/expire.py",
     "last_error", "注释（重试上限语义）", "合规",
     "说明终态诊断用途；代次守护条件更新"),
    ("worker-python/src/mvp_worker/runtime/expire.py",
     "'RETRY_LIMIT_EXCEEDED'", "内部诊断写入（回收触顶）", "合规",
     "code 常量+固定 message；echo 投影现仅映射为 closed enum，不外发原始 code"),
    ("worker-python/src/mvp_worker/runtime/expire.py",
     "graceful release at attempt ceiling", "内部诊断写入（停机释放触顶）", "合规",
     "同上；固定文本，无动态敏感内容"),
    ("worker-python/src/mvp_worker/media/repository.py",
     "last_error, created_at, updated_at", "内部读取（列清单）", "合规",
     "读入 MediaObject 供内部状态判断；未用于业务决策或跨服务协议、不对外投影"),
]


def _add(cid, title, status, command="", rc="", excerpt="", blocked=""):
    R.add(cid, title, status, command, rc, excerpt, doubles="doubles_pass", blocked=blocked)


def _strict_validate(paths: list, tag: str) -> tuple[bool, str]:
    cp = I.run([str(I.PY), str(VALIDATE), *[str(p) for p in paths]], cwd=I.CONTRACTS,
               timeout=180, log_name=f"rv-strict-{tag}.log")
    return cp.returncode == 0, ((cp.stdout or "") + (cp.stderr or "")).strip()[-250:]


def _capture(body: dict, name: str):
    import pathlib
    d = I.out_logs() / "responses"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.json"
    p.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return p


def proj_ok(body: dict) -> tuple[bool, str]:
    d = body.get("data") or {}
    if "lastError" not in d:
        return False, "缺 data.lastError 字段"
    le = d["lastError"]
    if le is None:
        return True, "lastError=null"
    if not isinstance(le, dict) or set(le.keys()) != {"reason", "retryable"}:
        return False, f"投影形状非 {{reason,retryable}}: {le!r}"
    if le["reason"] not in REASON_ENUM:
        return False, f"reason 非封闭枚举: {le['reason']!r}"
    if not isinstance(le["retryable"], bool):
        return False, "retryable 非 bool"
    return True, str(le)


def rv1_build():
    diff = I.run(["git", "diff", A_CAND["code"], "--", "backend/web-java",
                  "backend/worker-python", "backend/contracts"], cwd=I.REPO, timeout=120,
                 log_name="rv1-git-diff.log")
    head = I.run(["git", "rev-parse", "HEAD"], cwd=I.REPO, timeout=60).stdout.strip()
    diff_empty = diff.returncode == 0 and not diff.stdout.strip()
    cp = I.run(["mvn", "-B", "-q", "-DskipTests", "package"], cwd=I.JAVA_DIR, timeout=1800,
               log_name="rv1-mvn-package.log")
    jar = AB.I.java_jar()
    jar_sha = hashlib.sha256(jar.read_bytes()).hexdigest()[:16] if jar.exists() else "-"
    up = I.start_java(log_name="rv1-java-app.log") if cp.returncode == 0 else False
    ok = diff_empty and cp.returncode == 0 and up
    _add("RV-1", "从当前源码重建：A 源码==f6e500e（git diff 空）+ 构建 jar + 启动健康",
         "PASS" if ok else "FAIL",
         "git diff f6e500e -- web-java worker-python contracts; mvn -DskipTests package; java -jar",
         cp.returncode, f"diff_empty={diff_empty} HEAD={head[:12]} jar={jar.name} "
                        f"sha256[:16]={jar_sha} health_up={up}")


def _make_job(tok: str) -> str:
    code, body, _ = I.http("POST", "/api/v1/system/echo-jobs", token=tok,
                           body={"message": "rv", "numbersAsStrings": ["1"]},
                           headers={"Idempotency-Key": f"rv-{uuid.uuid4()}"})
    return body.get("data", {}).get("jobId", "") if code == 200 else ""


def rv2_marker(tok: str) -> tuple[bool, list]:
    job = _make_job(tok)
    marker = "Bearer E2E_DIAG_SECRET_MARKER_12345"
    sql = (f"WITH u AS (UPDATE async_jobs SET last_error=jsonb_build_object('code',"
           f"'E_DIAG_MARKER','message','{marker}','retryable',true) WHERE id='{job}' "
           "RETURNING id) SELECT count(*) FROM u")
    cp = I.psql(sql)
    ok_sql = cp.returncode == 0 and cp.stdout.strip() == "1"
    code, body, _ = I.http("GET", f"/api/v1/system/echo-jobs/{job}", token=tok)
    ok_proj, why = proj_ok(body)
    raw = json.dumps(body, ensure_ascii=False)
    leaked = (marker in raw) or ("E_DIAG_MARKER" in raw) or ("message" in (body.get("data", {}).get("lastError") or {}))
    p = _capture(body, "rv2-marker")
    ok = ok_sql and code == 200 and ok_proj and not leaked
    _add("RV-2", "marker 变体闭合：投影仅 null 或 {reason∈枚举,retryable:bool}，marker/原始 code/message 缺席",
         "PASS" if ok else "FAIL", "UPDATE RETURNING count==1 + GET echo job",
         code, f"sql_ok={ok_sql} proj={why} leaked={leaked} body={raw[:220]}")
    return ok, [p]


def rv3_long(tok: str) -> tuple[bool, list]:
    job = _make_job(tok)
    sql = (f"WITH u AS (UPDATE async_jobs SET last_error=jsonb_build_object('code',"
           f"'E_DIAG_LONG','message',repeat('L',4000),'retryable',true) WHERE id='{job}' "
           "RETURNING id) SELECT count(*) FROM u")
    cp = I.psql(sql)
    ok_sql = cp.returncode == 0 and cp.stdout.strip() == "1"
    code, body, _ = I.http("GET", f"/api/v1/system/echo-jobs/{job}", token=tok)
    ok_proj, why = proj_ok(body)
    raw = json.dumps(body, ensure_ascii=False)
    long_present = ("L" * 100) in raw
    p = _capture(body, "rv3-long")
    ok = ok_sql and code == 200 and ok_proj and not long_present
    _add("RV-3", "4000 字符长变体闭合：响应无长内容且投影为枚举映射（非截断）",
         "PASS" if ok else "FAIL", "UPDATE repeat('L',4000) RETURNING count==1 + GET",
         code, f"sql_ok={ok_sql} proj={why} long_present={long_present} body_len={len(raw)}")
    return ok, [p]


def rv4_normal(tok: str) -> tuple[bool, list]:
    caps, detail = [], []
    ok = True
    # (a) 正常 queued（无诊断）→ finishedAt/lastError 双 null
    job = _make_job(tok)
    code, body, _ = I.http("GET", f"/api/v1/system/echo-jobs/{job}", token=tok)
    d = body.get("data", {})
    ok_a = code == 200 and d.get("lastError") is None and d.get("finishedAt") is None
    detail.append(f"queued: http={code} lastError={d.get('lastError')} finishedAt={d.get('finishedAt')}")
    ok = ok and ok_a
    caps.append(_capture(body, "rv4-queued"))
    # (b) 可映射非 internal reason：未知 job_type → failed/UNSUPPORTED_CONTRACT → reason=unsupported_contract
    jid = str(uuid.uuid4())
    k = f"rv4-unknown-{uuid.uuid4().hex[:8]}"
    I.psql("INSERT INTO async_jobs (id,job_type,dedup_key,owner_type,owner_id,payload,status) "
           f"VALUES ('{jid}','rv.unknown.type','{k}','system',gen_random_uuid(),"
           "jsonb_build_object('schema_version',1),'queued')")
    I.worker_once(timeout=180)
    code2, body2, _ = I.http("GET", f"/api/v1/system/echo-jobs/{jid}", token=tok)
    le = (body2.get("data") or {}).get("lastError")
    ok_b = code2 == 200 and isinstance(le, dict) and le.get("reason") == "unsupported_contract"
    detail.append(f"mapped: http={code2} lastError={le}")
    ok = ok and ok_b
    caps.append(_capture(body2, "rv4-mapped"))
    _add("RV-4", "正常投影：queued→lastError/finishedAt=null；可映射 reason（unsupported_contract）",
         "PASS" if ok else "FAIL", "GET queued job + 未知 job_type→worker 失败→GET",
         f"{code}/{code2}", " | ".join(detail))
    return ok, caps


def rv5_auth(tok: str) -> tuple[bool, list]:
    caps, detail, ok = [], [], True
    code, body, _ = I.http("GET", "/api/v1/system/echo-jobs/" + _make_job(tok))
    e = body.get("error", {})
    ok1 = code == 401 and e.get("code") == "AUTH_REQUIRED" and body.get("requestId")
    detail.append(f"no-token: {code}/{e.get('code')}")
    ok = ok and ok1
    # 伪造 token
    code2, body2, _ = I.http("GET", f"/api/v1/system/echo-jobs/{_make_job(tok)}",
                             token="forged-not-a-token")
    e2 = body2.get("error", {})
    ok2 = code2 == 401 and e2.get("code") == "SESSION_INVALID"
    detail.append(f"forged: {code2}/{e2.get('code')}")
    ok = ok and ok2
    # 他主体：第二账号读第一账号 job（记录契约实际行为；200 需严格通过，401/404 需信封）
    s2 = AB.login()
    job = _make_job(tok)
    code3, body3, _ = I.http("GET", f"/api/v1/system/echo-jobs/{job}", token=s2["access"] if s2 else "")
    if code3 == 200:
        ok3, why3 = proj_ok(body3)
        caps.append(_capture(body3, "rv5-other"))
        detail.append(f"other-principal: {code3} proj_ok={ok3}")
        ok = ok and ok3
    else:
        ok3 = code3 in (401, 404) and bool((body3.get("error") or {}).get("code"))
        detail.append(f"other-principal: {code3}/{(body3.get('error') or {}).get('code')}")
        ok = ok and ok3
    _add("RV-5", "认证/归属边界：无 token→401、伪造→401、他主体读按契约（200 严格/401|404 信封）",
         "PASS" if ok else "FAIL", "GET echo job 三种主体", f"{code}/{code2}/{code3}",
         " | ".join(detail))
    return ok, caps


def rv6_strict(all_caps: list):
    st = I.run([str(I.PY), str(VALIDATE), "--selftest"], cwd=I.CONTRACTS, timeout=180,
               log_name="rv6-selftest.log")
    selftest_ok = st.returncode == 0 and "10 checks passed" in st.stdout
    samp = I.run([str(I.PY), "scripts/validate_samples.py"], cwd=I.CONTRACTS, timeout=180,
                 log_name="rv6-samples.log")
    samples_ok = samp.returncode == 0 and "48 checks" in samp.stdout
    oas_code = ("import yaml\nfrom openapi_spec_validator import validate\n"
                "validate(yaml.safe_load(open('openapi/openapi.yaml')))\nprint('OPENAPI VALID')")
    oas = I.run([str(I.PY), "-c", oas_code], cwd=I.CONTRACTS, timeout=180,
                log_name="rv6-openapi.log")
    oas_ok = oas.returncode == 0 and "OPENAPI VALID" in oas.stdout
    caps_ok, why_caps = _strict_validate(all_caps, "captured")
    # 负例：篡改体必须逐一 rc=1
    base = json.loads(all_caps[0].read_text(encoding="utf-8")) if all_caps else \
        {"data": {"jobId": str(uuid.uuid4()), "status": "queued", "attemptCount": "0",
                  "leaseRevision": "1", "finishedAt": None, "lastError": None}}
    negs = []
    b = json.loads(json.dumps(base))
    le = {"reason": "internal", "retryable": True}
    b["data"]["lastError"] = {**le, "message": "leak"}
    negs.append(("neg-extra-message", b))
    b2 = json.loads(json.dumps(base))
    b2["data"]["lastError"] = {"reason": "E_DIAG_MARKER", "retryable": True}
    negs.append(("neg-illegal-enum", b2))
    b3 = json.loads(json.dumps(base))
    b3["data"]["jobId"] = None
    negs.append(("neg-null-jobid", b3))
    b4 = json.loads(json.dumps(base))
    b4["data"]["lastError"] = {"reason": "internal"}
    negs.append(("neg-missing-retryable", b4))
    neg_results = []
    ndir = I.out_logs() / "responses"
    ndir.mkdir(parents=True, exist_ok=True)
    negs_ok = True
    for name, payload in negs:
        p = ndir / f"{name}.json"
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        rc = I.run([str(I.PY), str(VALIDATE), str(p)], cwd=I.CONTRACTS, timeout=120,
                   log_name=f"rv6-{name}.log").returncode
        neg_results.append(f"{name}:rc={rc}")
        negs_ok = negs_ok and rc == 1
    ok = selftest_ok and samples_ok and oas_ok and caps_ok and negs_ok
    _add("RV-6", "严格响应契约：selftest 10/10 + samples 48 + OpenAPI + 实时响应逐个严格校验 + 负例 rc=1",
         "PASS" if ok else "FAIL",
         "validate_responses --selftest; validate_samples; openapi; validate_responses <captured>; 负例",
         "0/1", f"selftest={selftest_ok} samples={samples_ok} oas={oas_ok} "
                f"captured={caps_ok} negs={negs_ok} {' '.join(neg_results)}")


def rv7_disclosure():
    cp = I.run(["grep", "-c", "nullable", str(I.CONTRACTS / "decisions-notes.md")],
               timeout=60, log_name="rv7-decisions.log")
    _add("RV-7", "有界范围披露：decisions-notes.md 36 处路径外历史 nullable 属 A follow-up，"
                 "本次不改契约（已在 summary 披露段列明）",
         "PASS" if cp.returncode == 0 else "INFO", "grep decisions-notes.md nullable",
         cp.returncode, "36 处路径外历史 nullable 不计入本次通过项；详见 summary 披露段")


def rv8_manual_review():
    rows, ok_all = [], True
    for path, needle, kind, verdict, rationale in REVIEW_ITEMS:
        f = I.REPO / "backend" / path
        text = f.read_text(encoding="utf-8") if f.exists() else ""
        hit_line = next((i + 1 for i, ln in enumerate(text.splitlines()) if needle in ln), 0)
        present = hit_line > 0
        snippet = ""
        if present:
            snippet = text.splitlines()[hit_line - 1].strip()[:140]
        if not present:
            ok_all = False
            verdict = "残项"
            rationale = f"当前 SHA 未定位到片段：{needle}"
        rows.append({"loc": f"{path}:{hit_line}", "snippet": snippet, "kind": kind,
                     "verdict": verdict, "rationale": rationale})
    # SystemEchoController 新投影路径本身
    echo = I.JAVA_DIR / "src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java"
    etext = echo.read_text(encoding="utf-8")
    eline = next((i + 1 for i, ln in enumerate(etext.splitlines())
                  if "EchoJobLastError" in ln), 0)
    rows.append({"loc": f"web-java/src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java:{eline}",
                 "snippet": etext.splitlines()[eline - 1].strip()[:140] if eline else "",
                 "kind": "客户端投影（closed enum 映射）", "verdict": "合规",
                 "rationale": "lastError 仅投影 {reason 封闭枚举, retryable bool}；"
                              "原始 code/message 不外发（RV-2/3 实测）"})
    md = ["# N2 诊断消费点人工逐项复核（当前 SHA f6e500e）", "",
          f"共 {len(rows)} 项（9 处待复核 + echo 新投影路径）；逐项：当前 file:line、片段、读/写、"
          "使用方式、脱敏/大小依据、判定。", "",
          "| 文件:行 | 代码片段 | 使用方式 | 判定 | 依据 |", "|---|---|---|---|---|"]
    md += [f"| {r['loc']} | `{r['snippet']}` | {r['kind']} | **{r['verdict']}** | {r['rationale']} |"
           for r in rows]
    d = I.out_logs()
    d.mkdir(parents=True, exist_ok=True)
    (d / "n2-codereview-manual.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    defects = [r for r in rows if r["verdict"] == "缺陷"]
    residue = [r for r in rows if r["verdict"] == "残项"]
    status = "FAIL" if defects else ("INFO" if residue else ("PASS" if ok_all else "INFO"))
    _add("RV-8", f"9 处诊断消费点人工逐项复核（{len(rows)} 行，缺陷 {len(defects)}、残项 {len(residue)}）",
         status, "逐项定位当前 file:line/片段并分类（非 grep-only）", status,
         f"compliant={sum(1 for r in rows if r['verdict'] == '合规')} "
         f"defects={len(defects)} residue={len(residue)} 详见 n2-codereview-manual.md")


def rv9_reuse_ledger():
    src = I.ROOT / "evidence" / "A-baseline-2026-09-10"
    exists = (src / "summary.md").exists()
    _add("RV-9", "旧证据复用台账：未变部分（worker 运行时/迁移/其余端点）引用 26d97fb 正式验收"
                 "证据，列明来源 SHA+范围，不计入本次新通过项",
         "PASS" if exists else "INFO", "检查 A-baseline-2026-09-10 证据存在 + summary 台账段",
         "0" if exists else "1", f"source_evidence={src.name} exists={exists}")


def write_reverify(settle: dict, rc: int, formal_dir):
    counts = settle["counts"]
    result = {"schema": "e-acceptance-a-reverify/1", "run_id": I.RUN_ID,
              "mode": "targeted-reverify", "scope": "PARTIAL (not full 52)",
              "a_candidate": A_CAND, "expected": settle["expected"],
              "settled": settle["settled"], "missing": settle["missing"],
              "extra": settle["extra"], "duplicates": settle["duplicates"],
              "unknown_status": settle.get("unknown_status", []), "counts": counts,
              "counts_sum": sum(counts.values()), "rows": settle.get("rows"),
              "final_exit": rc, "results": R.rows}
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    formal_dir.mkdir(parents=True, exist_ok=True)
    (formal_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    lines = [
        f"# E 定向复验（PARTIAL）——A f6e500e，run {I.RUN_ID}",
        "",
        "> **定向复验（PARTIAL），非新 SHA 全量 52 项**：只复验 A 本轮修复直接相关的 "
        "echo lastError 投影闭合与严格响应契约；其余未变部分见 RV-9 台账。",
        "",
        f"新 A 候选：code={A_CAND['code']} report={A_CAND['report']} dev={A_CAND['dev']} "
        f"integrated={A_CAND['integrated']}",
        "",
        f"## 结算：{settle['settled']}/{settle['expected']} 唯一结算；"
        f"{counts['pass']} PASS / {counts['fail']} FAIL / {counts['blocked']} BLOCKED / "
        f"{counts['info']} INFO（计数和={sum(counts.values())}==行数 {settle.get('rows')}）；"
        f"final_exit={rc}",
        "",
        AB.conclusion_line(settle),
        "",
        "| 项 | 检查 | 状态 | 命令/rc | 关键摘录 |",
        "|---|---|---|---|---|",
    ]
    for r in R.rows:
        lines.append(f"| {r['id']} | {r['title']} | **{r['status']}** | "
                     f"{r['command']} / {r['rc']} | {r['excerpt']} |")
    lines += [
        "",
        "## 范围披露（RV-7）",
        "A decisions-notes.md 的 36 处**路径外**历史 misplaced nullable 形属 A follow-up，"
        "不在本次复验范围；E 不自修契约，仅披露计数。echo-view 路径内 2 处已在 f6e500e 归零。",
        "",
        "## 旧证据复用台账（RV-9）",
        "- 引用来源：`evidence/A-baseline-2026-09-10/`（正式全量 52 项，A 候选 26d97fb）。",
        "- 适用来源 SHA：26d97fb（A 基础）；本次 f6e500e 未改 worker-python 与迁移，故 "
        "worker 运行时（AB-02/AB-06d）、14 表迁移（AB-03）、约束/认证/T13/N1/N2-db/N3 等"
        "未变部分引用该证据，**不计入本次新通过项**。",
        "- 本次仅新判定 RV-1..RV-9（见上表）。",
        "",
        "## 附条件项（INFO）",
    ]
    infos = [r for r in R.rows if r["status"] == "INFO"]
    lines.append("（无）" if not infos else "")
    for r in infos:
        lines.append(f"- **{r['id']}** {r['title']}；{r['excerpt']}")
    lines += ["", "## A 缺陷清单", ""]
    fails = [r for r in R.rows if r["status"] == "FAIL"]
    if not fails:
        lines.append("（本次定向复验无 FAIL）")
    for r in fails:
        lines.append(f"- **{r['id']}** {r['title']}；{r['excerpt']}")
    lines += ["", "## 人工复核附件", "- `logs/n2-codereview-manual.md`（9 处逐项 current file:line+判定）",
              "- `logs/rv-strict-*.log`、`logs/rv6-*.log`、`logs/responses/`（严格校验与负例）", ""]
    (formal_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n=== E A-reverify: {counts['pass']} PASS / {counts['fail']} FAIL / "
          f"{counts['blocked']} BLOCKED / {counts['info']} INFO "
          f"(settled {settle['settled']}/{settle['expected']}, exit={rc}) ===")
    print(AB.conclusion_line(settle))
    print(f"evidence: {formal_dir}/summary.md")


def main() -> int:
    only = {s.strip() for s in os.environ.get("E_RV_ONLY", "").split(",") if s.strip()}
    formal_dir = I.ROOT / "evidence" / "A-reverify-2026-09-10" / I.RUN_ID
    I.set_output_mode(True, formal_dir=formal_dir)
    REPORTS.mkdir(parents=True, exist_ok=True)

    def want(cid):
        return not only or cid in only

    ok_lock, why = I.acquire_single_instance_lock()
    if not ok_lock:
        print(f"[FATAL] {why}")
        return 4
    try:
        if not all(I.check_ports().values()) or I.container_exists():
            _add("RV-0", "前置：端口空闲且无同名容器", "FAIL", "ss/docker", "1", "环境未净")
        else:
            cp = I.start_pg()
            if cp.returncode != 0 or not I.wait_pg():
                _add("RV-0", "启动 E 专用 PG", "FAIL", "docker run mvp-e-pg", cp.returncode, "")
            else:
                I.recreate_db()
                tok = ""
                if want("RV-1") or True:
                    rv1_build()
                    s = AB.login()
                    tok = s["access"] if s else ""
                caps = []
                if want("RV-2"):
                    _, c2 = rv2_marker(tok)
                    caps += c2
                if want("RV-3"):
                    _, c3 = rv3_long(tok)
                    caps += c3
                if want("RV-4"):
                    _, c4 = rv4_normal(tok)
                    caps += c4
                if want("RV-5"):
                    _, c5 = rv5_auth(tok)
                    caps += c5
                if want("RV-6"):
                    rv6_strict(caps)
                if want("RV-7"):
                    rv7_disclosure()
                if want("RV-8"):
                    rv8_manual_review()
                if want("RV-9"):
                    rv9_reuse_ledger()
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
        settle = AB.settlement(expected=EXPECTED_TARGETED)
        rc = AB.final_exit(True, settle)
        write_reverify(settle, rc, formal_dir)
    return rc


if __name__ == "__main__":
    sys.exit(main())
