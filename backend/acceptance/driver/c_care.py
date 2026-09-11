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
                   "parameter_ranges": {"intensity": {"min": "0", "max": "5", "unit": "level"},
                                        "vendor_debug": {"min": "0", "max": "5", "unit": "level"}},
                   "approved_regions": ["face"], "n_bounds": {"min": "1", "max": "30"}}})
DEFAULT_CAPABILITIES = json.dumps({
    "schema_version": 1, "capability_id": "cap-mvp-1", "revision": "9",
    "parameter_ranges": {"intensity": {"min": "0", "max": "8", "unit": "level"},
                         "vendor_debug": {"min": "0", "max": "8", "unit": "level"}},
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
#: 同一份敏感 summary（走 A01 列表 / T07 快照 summary / A09 摘要），覆盖白名单与禁项。
SENSITIVE_SUMMARY = json.dumps({
    "schema_version": 1, "title": "完整方案", "description": "d",
    "provider_raw_response": "SECRET1", "source_report_id": "rep-1",
    "SECRET8": "x"})

CARE = "/api/v1"

#: 契约 OAS 严格校验（成功响应）。validate_responses.py 仅支持 echo；这里复用其
#: OAS 3.0.3→JSON Schema 转换器 `convert`，对任意 path/method/status 解析真实 schema。
_OAS_DOC: dict | None = None
_OAS_CONVERT = None


def _oas_convert():
    global _OAS_CONVERT
    if _OAS_CONVERT is None:
        import importlib.util
        p = I.CONTRACTS / "scripts" / "validate_responses.py"
        spec = importlib.util.spec_from_file_location("validate_responses_mod", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _OAS_CONVERT = mod.convert
    return _OAS_CONVERT


def oas_schema_strict(node, doc):
    """OAS 3.0.3 → JSON Schema，**严格复用 RV-6 转换器**（不改变 OAS 语义）。

    对齐 A 轮 `contracts/scripts/validate_responses.py::convert` 既有规则：`nullable`
    仅作用于同一 Schema Object 的本地 `type`；`$ref`/`allOf` 保持原结构、不展平；
    `allOf` 交由 jsonschema 原生组合语义（`additionalProperties:false` 分支不合并兄弟属性）。
    """
    return _oas_convert()(node, doc)


def oas_errors_node(node, doc, body):
    from jsonschema import Draft202012Validator
    schema = oas_schema_strict(node, doc)
    return sorted(Draft202012Validator(schema).iter_errors(body),
                  key=lambda e: list(e.absolute_path))


#: R17：13 条契约建模缺陷精确 allowlist（真四元组：API + 归一化实例路径 + validator +
#: absolute_schema_path）。从实际观测错误（0972884c/735fb16d 的 cc-11-captured.json）派生，
#: 硬编码 schema path；任何字段不符（含 schema path 变化）一律 impl → CC-11 FAIL。
_NULLABLE_CTX = "nullable:true 与 $ref/allOf 同层（OAS 3.0.3 不生效）→ C 按契约意图返回 null"
CC11_CONTRACT_ALLOWLIST = {
    ("A01", "$.data.items[*].progress.completedAt", "type",
     ("allOf", 1, "properties", "data", "allOf", 1, "properties", "items", "items",
      "properties", "progress", "allOf", 0, "properties", "completedAt", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ Progress.completedAt",
    ("A02", "$.data.progress.completedAt", "type",
     ("allOf", 1, "properties", "data", "properties", "progress", "allOf", 0,
      "properties", "completedAt", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ Progress.completedAt",
    ("A03", "$.data.controller.gimbalId", "type",
     ("allOf", 1, "properties", "data", "properties", "controller", "properties",
      "gimbalId", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ ControllerRef.gimbalId",
    ("A03", "$.data.progress.completedAt", "type",
     ("allOf", 1, "properties", "data", "properties", "progress", "properties",
      "completedAt", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ Progress.completedAt",
    ("A03", "$.data.verification.validUntil", "type",
     ("allOf", 1, "properties", "data", "properties", "verification", "properties",
      "validUntil", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ Verification.validUntil",
    ("A04", "$.data.progress.completedAt", "type",
     ("allOf", 1, "properties", "data", "properties", "progress", "properties",
      "completedAt", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ Progress.completedAt",
    ("A04", "$.data.verification.validUntil", "type",
     ("allOf", 1, "properties", "data", "properties", "verification", "properties",
      "validUntil", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ Verification.validUntil",
    ("A05", "$.data.progress.completedAt", "type",
     ("allOf", 1, "properties", "data", "properties", "progress", "allOf", 0,
      "properties", "completedAt", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ Progress.completedAt",
    ("A07", "$.data.controller.gimbalId", "type",
     ("allOf", 1, "properties", "data", "properties", "controller", "allOf", 0,
      "properties", "gimbalId", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ ControllerRef.gimbalId",
    ("A07", "$.data.progress.completedAt", "type",
     ("allOf", 1, "properties", "data", "properties", "progress", "allOf", 0,
      "properties", "completedAt", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ Progress.completedAt",
    ("A08", "$.data.completedAt", "type",
     ("allOf", 1, "properties", "data", "allOf", 0, "properties", "completedAt",
      "allOf", 0, "type")):
        _NULLABLE_CTX + " @ Progress.completedAt",
    ("A09", "$.data.items[*].closedAt", "type",
     ("allOf", 1, "properties", "data", "allOf", 1, "properties", "items", "items",
      "properties", "closedAt", "allOf", 0, "type")):
        _NULLABLE_CTX + " @ CareExecutionListItem.closedAt",
    ("A08", "$.data", "additionalProperties",
     ("allOf", 1, "properties", "data", "allOf", 0, "additionalProperties")):
        "allOf: ProgressWithSync.lastSyncedAt 被 Progress.additionalProperties:false 误伤",
}


def normalize_json_path(json_path):
    return re.sub(r"\[\d+\]", "[*]", json_path or "$")


def unknown_fields_of_additional_properties(err):
    """结构化计算 additionalProperties 的未知字段集合（不解析人类可读 message）。

    unknown = set(instance.keys()) − set(schema.properties) − patternProperties 匹配项。
    `err.instance` 为被测对象、`err.schema` 为含 `additionalProperties:false` 的分支 schema。
    与字段名是否含引号等字符完全无关，杜绝 message 正则被合法字段名绕过。
    """
    inst = err.instance
    if not isinstance(inst, dict):
        return set()
    schema = err.schema if isinstance(err.schema, dict) else {}
    props = schema.get("properties") or {}
    patterns = schema.get("patternProperties") or {}
    unknown = set()
    for key in inst.keys():
        if key in props:
            continue
        if isinstance(patterns, dict) and any(re.search(pat, key) for pat in patterns):
            continue
        unknown.add(key)
    return unknown


def classify_strict_error(api, err):
    """R17 精确分类：真四元组（API+归一化路径+validator+schema path）精确命中且上下文
    成立 → contract；否则（含 allowlist 外、schema path 变化、额外未知字段）impl→FAIL。"""
    key = (api, normalize_json_path(err.json_path), err.validator,
           tuple(err.absolute_schema_path))
    ctx = CC11_CONTRACT_ALLOWLIST.get(key)
    if ctx is None:
        return "impl-or-other"
    if err.validator == "type" and err.instance is not None:
        return "impl-or-other"           # 非 null 的 type 违规不接受
    if err.validator == "additionalProperties" and \
            unknown_fields_of_additional_properties(err) != {"lastSyncedAt"}:
        return "impl-or-other"           # 未知字段集合必须恰为 {lastSyncedAt}
    return "contract:" + ctx


def oas_validate(path, method, status, body):
    """严格按 OAS（status 对应响应 schema）校验成功响应体。返回 (ok, detail)。"""
    global _OAS_DOC
    if _OAS_DOC is None:
        import yaml
        _OAS_DOC = yaml.safe_load((I.CONTRACTS / "openapi" / "openapi.yaml").read_text("utf-8"))
    node = _OAS_DOC["paths"][path][method]["responses"][str(status)]["content"][
        "application/json"]["schema"]
    errs = oas_errors_node(node, _OAS_DOC, body)
    if not errs:
        return True, ""
    detail = "; ".join(f"{e.json_path or '$'}: {e.validator or 'schema'} violated"
                       for e in errs[:4])
    return False, detail


def oas_errors_path(path, method, status, body):
    """按实际 HTTP status 取 OAS 响应 schema 并返回严格校验错误列表。"""
    global _OAS_DOC
    if _OAS_DOC is None:
        import yaml
        _OAS_DOC = yaml.safe_load((I.CONTRACTS / "openapi" / "openapi.yaml").read_text("utf-8"))
    node = _OAS_DOC["paths"][path][method]["responses"][str(status)]["content"][
        "application/json"]["schema"]
    return oas_errors_node(node, _OAS_DOC, body)


def cc11_outcome(baseline_ok, captured, status_bad, impl_bad, contract_issues):
    """CC-11 结论纯函数：
    - 严格全过 → PASS；
    - 仅契约建模问题（nullable over $ref/allOf、allOf+additionalProperties）→ INFO（附条件，
      如实披露精确字段路径与归属，**不静默放宽**）；
    - 状态不符或疑似实现缺陷 → FAIL。
    """
    if not baseline_ok or captured != 9 or status_bad or impl_bad:
        return "FAIL"
    if contract_issues:
        return "INFO"
    return "PASS"


def contains_schema_version(body) -> bool:
    return "schema_version" in json.dumps(body, ensure_ascii=False)


def read_log(name: str) -> str:
    p = REPORTS / name
    return p.read_text(errors="replace") if p.exists() else ""


def cc03_failfast_reason(label: str, log_text: str):
    """CC-03 每变体具体 fail-fast 签名判定（纯函数，供 selfcheck 回归）。

    返回 (ok, signature)。要求命中**本变体专属的生产/绑定拒绝签名**，且**绝不**
    包含成功启动标记；无关原因（构建错误/DB 故障/端口占用等）不匹配 → FAIL。
    """
    if "Started WebJavaApplication" in log_text:
        return False, "started_ok"
    production_provider = any(k in log_text for k in (
        "SessionProvider", "SmsCodeProvider", "DeviceCredentialProvider",
        "FaceProvider", "StoragePort")) and (
        "No qualifying bean" in log_text or "APPLICATION FAILED TO START" in log_text)
    validator = "ProductionFailClosedValidator" in log_text or "production fail-closed" in log_text
    guard = "CareFaceVerifierProductionGuard" in log_text
    uuid_fail = ("MemberBindingFaceDouble" in log_text
                 and ("must be a UUID or blank" in log_text or "Invalid UUID string" in log_text))
    if label in ("prod-only", "prod,dev+bound"):
        if validator or guard:
            return True, "validator/guard"
        if production_provider:
            # prod profile → app.providers.mode=real → 替身禁用、缺真实 provider bean，
            # Spring 在 APPLICATION FAILED TO START 前拒绝（未及 Validator afterSingletons）。
            return True, "real-provider-required"
        return False, "no_production_signature"
    if label == "dev+APP_ENV=production":
        return (True, "ProductionFailClosedValidator") if validator else \
            (False, "no_production_signature")
    if label == "dev+invalid-bound":
        return (True, "uuid_parse_failfast") if uuid_fail else (False, "no_uuid_signature")
    return False, "unknown_variant"


#: CC-05 五面落点期望（A03 为 201，其余 200）。
CC05_LANDINGS = {"A01": 200, "A02": 200, "A03": 201, "A08": 200, "A09": 200}


def cc05_verdict(landing_status, hit, no_schema_version, vd_ok, regions_kept, full_kept,
                 a01_sum_ok, proj_ok, snap_ok, a09_ok):
    """CC-05 纯谓词：任一落点非期望状态、任一白名单保留/禁项/快照不满足 → 不得 PASS。"""
    landing_ok = all(landing_status.get(k) == v for k, v in CC05_LANDINGS.items())
    return bool(landing_ok and not hit and no_schema_version and vd_ok and regions_kept
                and full_kept and a01_sum_ok and proj_ok and snap_ok and a09_ok)


def cc06_variant_ok(status, code, reason, expected):
    """CC-06 单变体：必须 409 PLAN_NOT_READY 且 reason 精确等于期望 token。"""
    return status == 409 and code == "PLAN_NOT_READY" and reason == expected


def cc09_verdict(*, dup_ok, k9_ok, k10_ok, k11_ok, gating_ok, conflict_ok,
                 stopped_ok, overflow_ok):
    return all([dup_ok, k9_ok, k10_ok, k11_ok, gating_ok, conflict_ok,
                stopped_ok, overflow_ok])


CC10_KEYS = ("stop_ok", "gaps_ok", "one_ok", "closed", "occ_rel", "replay_ok",
             "freeze_ok", "late_ok", "ack_ok", "still_close", "minimal", "get_2xx")


def cc10_verdict(**kw):
    return all(kw.get(k) is True for k in CC10_KEYS)


def cc11_verdict(baseline_ok, captured, status_bad, strict_bad):
    return bool(baseline_ok) and captured == 9 and not status_bad and not strict_bad


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
              revision=0, mc=None, summary=None):
    p = str(uuid.uuid4())
    payload = payload or CLEAN_PLAN
    summary = summary or '{"schema_version":1}'
    sql("INSERT INTO care_plans (id, assessment_id, member_id, generation_status, plan_summary,"
        " plan_payload, target_count, completed_count, progress_revision)"
        f" VALUES ('{p}','{assessment}','{member}','{status}',CAST('{summary}' AS jsonb),"
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

#: C 适用性证明范围 = C care 代码精确路径（C 编译产物语义）；契约面单独记录（B 错误码补丁）。
CC01_CARE_PATHS = ["backend/web-java/src/main/java/cn/yuanxin/mvp/web/care",
                   "backend/web-java/src/test/java/cn/yuanxin/mvp/web/care"]


def cc_01():
    head = I.run(["git", "rev-parse", "HEAD"], cwd=I.REPO, timeout=60).stdout.strip()
    anc = I.run(["git", "merge-base", "--is-ancestor", C_CODE, "HEAD"], cwd=I.REPO, timeout=60)
    diff = I.run(["git", "diff", f"{C_CODE}..HEAD", "--", *CC01_CARE_PATHS],
                 cwd=I.REPO, timeout=120, log_name="cc-01-diff.log")
    files = [x for x in diff.stdout.splitlines() if x.strip()]
    # 契约面：B 集成轮仅错误码声明补丁（非 C care 语义）；单独记录、不计入 C 适用性阻断。
    cdiff = I.run(["git", "diff", "--stat", f"{C_CODE}..HEAD", "--", "backend/contracts"],
                  cwd=I.REPO, timeout=120, log_name="cc-01-contracts-diff.log")
    contracts_changed = [x for x in cdiff.stdout.splitlines() if x.strip()]
    cp = I.run(["mvn", "-B", "-q", "-DskipTests", "package"], cwd=I.JAVA_DIR, timeout=1800,
               log_name="cc-01-mvn.log")
    jar = I.java_jar()
    import hashlib
    sha = hashlib.sha256(jar.read_bytes()).hexdigest()[:16] if jar.exists() else "-"
    ok = anc.returncode == 0 and files == [] and cp.returncode == 0
    _add("CC-01", "构建与启动绑定：8b3592e 祖先、**C care 域（care main/test）diff=0**"
                  "（C 代码未被 B/D/Swagger merge 改动）、当前源码构建、health UP@18081",
         "PASS" if ok else "FAIL", "git merge-base/diff（care 代码精确路径）; mvn package; java -jar",
         cp.returncode, f"HEAD={head[:12]} ancestor={anc.returncode == 0} "
                        f"care_code_diff={files} contracts_diff={contracts_changed} "
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
    sig_ok = {}

    def _sig_line(label, text):
        for line in reversed(text.splitlines()):
            low = line.lower()
            if any(k in line for k in ("ProductionFailClosedValidator", "production fail-closed",
                                       "No qualifying bean", "MemberBindingFaceDouble",
                                       "must be a UUID or blank", "APPLICATION FAILED TO START")):
                return line.strip()[:220]
        return ""

    def run_variant(label, env, log):
        proc, _up, clean = _restart_java(env, log, wait=False)
        if not clean or proc is None:
            I.stop_java()
            results.append(f"{label}: 环境未净（端口未释放），未启动，拒绝判定")
            sig_ok[label] = False
            return None
        try:
            rc = proc.wait(timeout=90)
        except Exception:
            rc = "running"
        I.stop_java()
        text = read_log(log)
        matched, signature = cc03_failfast_reason(label, text)
        refused = isinstance(rc, int) and rc != 0
        ok_variant = refused and matched
        sig_ok[label] = ok_variant
        results.append(f"{label}: rc={rc} refused={refused} sig={signature} "
                       f"evidence={_sig_line(label, text)!r}")
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
    # ①②③④ 负例变体（串行；每变体 env 显式构造 + 前置完全退出确认 + 具体 fail-fast 签名）
    r1 = run_variant("prod-only", variant_env(profiles="prod"), "cc-03-prod.log")
    r2 = run_variant("prod,dev+bound",
                     variant_env(profiles="prod,dev", bound_member=member), "cc-03-prod-dev.log")
    r3 = run_variant("dev+APP_ENV=production",
                     variant_env(profiles="dev", bound_member=member, app_env="production"),
                     "cc-03-dev-prod.log")
    r4 = run_variant("dev+invalid-bound",
                     variant_env(profiles="dev", bound_member="not-a-uuid"), "cc-03-bad.log")
    I.evidence_text("cc-03-variants.txt", "\n".join(results))
    # 生产拒绝断言不放宽：真实非零退出 **且** 命中本变体专属 fail-fast 签名
    ok = pos and all(sig_ok.get(k, False) for k in
                     ("prod-only", "prod,dev+bound", "dev+APP_ENV=production", "dev+invalid-bound"))
    _add("CC-03", "生产人脸 fail-closed：prod / prod,dev / dev+APP_ENV=production / 非法绑定 "
                  "拒绝启动且每变体命中具体 fail-fast 签名；dev 合法绑定正例 A03 201+T07 创建（判别力）",
         "PASS" if ok else "FAIL", "逐变体串行启动 JVM（限堆 640m）+ 日志签名断言",
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
    #           + T13=rejected + 同键重放同一拒绝（完整公开体等值）
    other_member = seed_member()
    seed_grant(ctx["accountId"], other_member)
    _restart_java(variant_env(profiles="dev", bound_member=other_member), "cc-04-foreign.log")
    a = AB.login()["access"]  # 重启后会话内存态重置，须重登
    fp, fmc = new_plan_and_mc(target=3)
    rows = scalar("SELECT count(*) FROM care_executions")
    keyf = str(uuid.uuid4())
    mdf = mk_metadata(fmc, plan=fp)
    c2, b2 = admit(a, fmc, fp, key=keyf, metadata=mdf)
    rows2 = scalar("SELECT count(*) FROM care_executions")
    t13f = scalar("SELECT status FROM idempotency_requests WHERE idempotency_key='" + keyf + "'")
    c2r, b2r = admit(a, fmc, fp, key=keyf, metadata=mdf)
    replay_equal = R5.canon_public(b2) == R5.canon_public(b2r)
    ok2 = (c2 == 403 and (b2.get("error") or {}).get("code") == "FACE_NOT_VERIFIED"
           and rows2 == rows and t13f == "rejected" and c2r == 403 and replay_equal)
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
                  "T07 零行+T13 rejected+同键重放等值拒绝；未绑定 503+T07 零行+T13 processing；"
                  "无客户端 memberId 输入路径",
         "PASS" if (ok1 and ok2 and ok3) else "FAIL",
         "三次 JVM 绑定切换 + A03 multipart",
         f"{c1}/{c2}/{c3}", f"bound201={ok1} foreign403={ok2}(rows {rows}->{rows2} t13={t13f} "
                             f"replay={c2r} equal={replay_equal}) "
                             f"unbound503={ok3}(rows {rows3a}->{rows3b} t13={t13}) "
                             f"noClientMemberField={no_member_field}")


# ---------------- CC-05 ----------------

def cc_05(ctx):
    a, member, plan, mc = ctx["tok"], ctx["member"], ctx["plan"], ctx["mc"]
    # 同一 SENSITIVE_PLAN 贯穿全链：A01 列表 → A02 full → A03 准入 → A08 progress → A09 历史
    c1, b1, _ = get_json(f"{CARE}/members/{member}/care-plans", a)
    c2, b2, _ = get_json(f"{CARE}/care-plans/{plan}?view=full", a)
    c3, b3 = admit(a, mc, plan, key=str(uuid.uuid4()))
    ex = (b3.get("data") or {}).get("executionId")
    c4, b4, _ = get_json(f"{CARE}/care-plans/{plan}/progress", a)
    c5, b5, _ = get_json(f"{CARE}/members/{member}/care-executions?planId={plan}", a)
    snap = scalar("SELECT plan_snapshot::text FROM care_executions WHERE id='" + str(ex or "") + "'")
    http_blob = json.dumps([b1, b2, b3, b4, b5], ensure_ascii=False)
    needles = ["SECRET1", "SECRET2", "SECRET3", "SECRET8", "provider_raw_response", "prompt"]
    hit = R5.forbidden_hit(http_blob + (snap or ""), needles)
    no_schema_version = not any(contains_schema_version(b) for b in (b1, b2, b3, b4, b5))

    def _find(body, key, value):
        for item in ((body.get("data") or {}).get("items") or []):
            if item.get(key) == value:
                return item
        return None

    a01 = _find(b1, "planId", plan)
    a09 = _find(b5, "executionId", ex)
    # A02 full：白名单保留 title/description/steps/regions/parameters + region 保留
    plan_full = ((b2.get("data") or {}).get("plan") or {})
    steps = plan_full.get("steps") or []
    vd2 = None
    try:
        vd2 = (steps[0].get("parameters") or {}).get("vendor_debug")
    except Exception:
        vd2 = None
    vd_ok = vd2 == {"value": "3", "unit": "level"}
    regions_kept = plan_full.get("regions") == ["face"]
    full_kept = (plan_full.get("title") == "完整方案" and isinstance(plan_full.get("steps"), list)
                 and bool(steps) and steps[0].get("region") == "face"
                 and isinstance(steps[0].get("parameters"), dict))
    # A01 summary 白名单保留（title/description/source_report_id），禁项与 schema_version 不出现
    a01_sum = (a01 or {}).get("planSummary") or {}
    a01_sum_ok = (a01 is not None and a01_sum.get("title") == "完整方案"
                  and a01_sum.get("source_report_id") == "rep-1"
                  and "provider_raw_response" not in a01_sum and "schema_version" not in a01_sum)
    # A03 执行投影：steps/regions/parameters 保留 + vendor_debug 收敛 {value,unit}
    proj = (b3.get("data") or {}).get("planExecution") or {}
    proj_steps = proj.get("steps") or []
    vd3 = None
    try:
        vd3 = (proj_steps[0].get("parameters") or {}).get("vendor_debug")
    except Exception:
        vd3 = None
    proj_ok = (bool(proj) and bool(proj_steps) and proj_steps[0].get("region") == "face"
               and vd3 == {"value": "3", "unit": "level"})
    # T07 快照：无禁项、保留 execution_params（steps/regions/parameters、vendor_debug 收敛）
    snap_ok = bool(snap) and "execution_params" in (snap or "") and "face" in (snap or "") \
        and "vendor_debug" in (snap or "") and "SECRET3" not in (snap or "")
    # A09 planSnapshotSummary 白名单保留
    a09_sum = (a09 or {}).get("planSnapshotSummary") or {}
    a09_ok = (a09 is not None and a09_sum.get("title") == "完整方案"
              and "provider_raw_response" not in a09_sum)
    ok = cc05_verdict({"A01": c1, "A02": c2, "A03": c3, "A08": c4, "A09": c5}, hit,
                      no_schema_version, vd_ok, regions_kept, full_kept, a01_sum_ok,
                      proj_ok, snap_ok, a09_ok) and bool(ex)
    I.evidence_text("cc-05-bodies.json", json.dumps(
        {"a01": b1, "a02": b2, "a03": b3, "a08": b4, "a09": b5,
         "t07_plan_snapshot": snap}, ensure_ascii=False, indent=2))
    _add("CC-05", "嵌套白名单五面+T07：同一 SENSITIVE_PLAN 贯穿 A01/A02/A03/A08/A09 全 2xx，"
                  "逐字节无 SECRET 键值、schema_version 不外发；白名单键与 region 保留、"
                  "vendor_debug 收敛 {value,unit}",
         "PASS" if ok else "FAIL", "SENSITIVE_PLAN 全链（列表/full/准入/progress/历史/T07 快照）",
         f"{c1}/{c2}/{c3}/{c4}/{c5}",
         f"forbidden_hit={hit} no_schema_version={no_schema_version} vd2={vd2} vd3={vd3} "
         f"regions_kept={regions_kept} full_kept={full_kept} a01_sum_ok={a01_sum_ok} "
         f"proj_ok={proj_ok} snapshot_len={len(snap or '')} snap_ok={snap_ok} a09_ok={a09_ok}")


# ---------------- CC-06 ----------------

def cc_06(ctx):
    a, member = ctx["tok"], ctx["member"]
    results = []

    def seed_and_admit(snapshot_mut=None, steps=None, device_caps=None, target=3,
                       frozen_mc=None):
        caps = device_caps if device_caps is not None else DEFAULT_CAPABILITIES
        mc = seed_microcrystal(caps)
        asmt = seed_assessment(ctx["gimbal"], member)
        if steps is None:
            steps = [{"region": "face", "parameters": {"intensity": "3"}}]
        payload = json.dumps({"schema_version": 1, "title": "t", "steps": steps})
        pid = str(uuid.uuid4())
        sql("INSERT INTO care_plans (id, assessment_id, member_id, generation_status, plan_summary,"
            f" plan_payload, target_count, completed_count, progress_revision) VALUES ('{pid}',"
            f"'{asmt}','{member}','ready',CAST('{{\"schema_version\":1}}' AS jsonb),"
            f"CAST('{payload}' AS jsonb),{target},0,0)")
        base = json.loads(DEFAULT_INPUT_SNAPSHOT)
        base["capability"]["microcrystal_id"] = frozen_mc or mc
        base["report"]["assessment_id"] = asmt
        if snapshot_mut:
            snapshot_mut(base)
        sql(f"UPDATE care_plans SET input_snapshot=CAST('{json.dumps(base)}' AS jsonb) WHERE id='{pid}'")
        return admit(a, mc, pid)

    def dev_caps(**over):
        d = json.loads(DEFAULT_CAPABILITIES)
        d.update(over)
        return json.dumps(d)

    M = "malformed_frozen_capability"
    variants = [
        ("capability={}", dict(snapshot_mut=lambda s: s.update(capability={})), M),
        ("缺 capability_id", dict(snapshot_mut=lambda s: s["capability"].pop("capability_id")), M),
        ("缺 parameter_ranges", dict(snapshot_mut=lambda s: s["capability"].pop("parameter_ranges")), M),
        ("缺 approved_regions", dict(snapshot_mut=lambda s: s["capability"].pop("approved_regions")), M),
        ("缺 n_bounds", dict(snapshot_mut=lambda s: s["capability"].pop("n_bounds")), M),
        ("单边缺 unit", dict(snapshot_mut=lambda s: s["capability"]["parameter_ranges"].__setitem__(
            "intensity", {"min": "0", "max": "5"})), M),
        ("min>max", dict(snapshot_mut=lambda s: s["capability"]["parameter_ranges"].__setitem__(
            "intensity", {"min": "9", "max": "5", "unit": "level"})), M),
        ("n_bounds 畸形(缺 max)", dict(snapshot_mut=lambda s: s["capability"].__setitem__(
            "n_bounds", {"min": "1"})), M),
        ("region 不支持", dict(snapshot_mut=lambda s: s["capability"].__setitem__(
            "approved_regions", ["ear"])), "region_not_supported"),
        ("冻结 capability 缺失", dict(snapshot_mut=lambda s: s.pop("capability")),
         "frozen_capability_requirement_missing"),
        ("设备能力缺失", dict(device_caps="{}"), "device_capabilities_missing"),
        ("capability_id 不等", dict(device_caps=dev_caps(capability_id="cap-other")),
         "capability_id_mismatch"),
        ("设备 unit 不等", dict(device_caps=dev_caps(parameter_ranges={
            "intensity": {"min": "0", "max": "8", "unit": "kg"}})), "parameter_range_not_covered"),
        ("设备范围不覆盖", dict(device_caps=dev_caps(parameter_ranges={
            "intensity": {"min": "0", "max": "4", "unit": "level"}})), "parameter_range_not_covered"),
        ("region∉设备支持", dict(snapshot_mut=lambda s: s["capability"].__setitem__(
            "approved_regions", ["face", "neck"]),
            device_caps=dev_caps(supported_regions=["face"])), "region_not_supported"),
        ("N∉n_bounds", dict(snapshot_mut=lambda s: s["capability"].__setitem__(
            "n_bounds", {"min": "5", "max": "10"})), "n_out_of_bounds"),
        ("步骤值出双侧区间", dict(steps=[{"region": "face", "parameters": {"intensity": "9"}}]),
         "step_parameters_not_covered"),
        ("步骤参数名未知", dict(steps=[{"region": "face", "parameters": {"foo": "1"}}]),
         "step_parameters_not_covered"),
        ("步骤参数 unit 不等", dict(steps=[{"region": "face", "parameters": {
            "intensity": {"value": "3", "unit": "kg"}}}]), "step_parameters_not_covered"),
        ("步骤缺 region", dict(steps=[{"parameters": {"intensity": "3"}}]),
         "malformed_frozen_step"),
        ("步骤 parameters 非对象", dict(steps=[{"region": "face", "parameters": "x"}]),
         "malformed_frozen_step"),
        ("steps 空数组", dict(steps=[]), "malformed_frozen_step"),
    ]
    observed, unmatched = set(), []
    for name, kw, expected in variants:
        c, b = seed_and_admit(**kw)
        code = (b.get("error") or {}).get("code")
        reason = ((b.get("error") or {}).get("details") or {}).get("reason")
        observed.add(reason)
        good = cc06_variant_ok(c, code, reason, expected)
        if not good:
            unmatched.append(name)
        results.append(f"{name}: status={c} code={code} reason={reason} expected={expected} ok={good}")
    # 正例判别力：冻结 revision=7≠设备 revision=9、microcrystal_id 与冻结不同、{value,unit} 严格相等
    c_pos, b_pos = seed_and_admit(frozen_mc=str(uuid.uuid4()))
    c_unit, _ = seed_and_admit(steps=[{"region": "face", "parameters": {
        "intensity": {"value": "3", "unit": "level"}}}])
    ok_pos = c_pos == 201 and c_unit == 201
    I.evidence_text("cc-06-details.txt", "\n".join(results))
    closed_enum = {"device_capabilities_missing", "frozen_capability_requirement_missing",
                   "malformed_frozen_capability", "capability_id_mismatch",
                   "parameter_range_not_covered", "region_not_supported", "n_out_of_bounds",
                   "step_parameters_not_covered", "malformed_frozen_step"}
    ok = not unmatched and ok_pos and observed <= closed_enum
    _add("CC-06", "能力严格 fail-closed：22 畸形/越界变体逐项 409 PLAN_NOT_READY 且 reason 命中"
                  "封闭 9-token 精确值；正例（冻结 rev≠设备 rev、microcrystal 不同、"
                  "{value,unit} 严格相等）201 判别力",
         "PASS" if ok else "FAIL", "逐变体新微晶/新方案种子 + A03（精确 token 断言）",
         f"pos={c_pos} unit={c_unit}",
         f"observed_tokens={sorted(t for t in observed if t)} variants={len(variants)} "
         f"unmatched={unmatched}")


# ---------------- CC-07/08/09/10: main execution lifecycle ----------------

def _new_ready_plan(member, target=3, payload=None, mc=None):
    asmt = seed_assessment(ctx_gimbal(), member)
    return seed_plan(asmt, member, "ready", payload, target=target)


def ctx_gimbal():
    return CONTEXT["gimbal"]


def cc_07_10(ctx):
    a, member = ctx["tok"], ctx["member"]
    import concurrent.futures as cf

    def on_mc(mc, target=3, payload=None):
        asmt = seed_assessment(CONTEXT["gimbal"], member)
        return seed_plan(asmt, member, "ready", payload, target=target, mc=mc)

    def srec(ex, ep, records, key=None):
        return sync(a, ex, {"records": records}, key or str(uuid.uuid4()))

    def sobs(ex, ep, seq, state, rev="1", continuity=True):
        return sync(a, ex, obs_body(ep, seq=seq, state=state, rev=rev, continuity=continuity),
                    str(uuid.uuid4()))

    def ecode(resp):
        return (resp[1].get("error") or {}).get("code")

    def ereason(resp):
        return ((resp[1].get("error") or {}).get("details") or {}).get("reason")

    def status_of(ex):
        return scalar(f"SELECT status FROM care_executions WHERE id='{ex}'")

    def acc_of(ex):
        return scalar(f"SELECT accepted_count FROM care_executions WHERE id='{ex}'")

    def comp_plan(pid):
        return scalar(f"SELECT coalesce(completed_at::text,'') FROM care_plans WHERE id='{pid}'")

    # ================= CC-07 幂等与重放 =================
    plan, mc = new_plan_and_mc(target=3)
    key = str(uuid.uuid4())
    md = mk_metadata(mc, plan=plan)
    c, b = admit(a, mc, plan, key=key, metadata=md)
    ex = (b.get("data") or {}).get("executionId")
    c_nokey, _ = post_multipart(f"{CARE}/care-executions", a, mk_metadata(mc, plan=plan), "")
    c_rep, b_rep = admit(a, mc, plan, key=key, metadata=md)
    same = (b_rep.get("data") or {}).get("executionId") == ex
    ver_rep = (b_rep.get("data") or {}).get("verification") or {}
    rev_before = scalar(f"SELECT verification_revision||'|'||coalesce(last_verified_at::text,'') "
                        f"FROM care_executions WHERE id='{ex}'")
    c_rep2, _ = admit(a, mc, plan, key=key, metadata=md)
    rev_after = scalar(f"SELECT verification_revision||'|'||coalesce(last_verified_at::text,'') "
                       f"FROM care_executions WHERE id='{ex}'")
    replayed = (b_rep.get("meta") or {}).get("replayed") is True and ver_rep.get("replayed") is True
    c_conf2, b_conf = post_multipart(f"{CARE}/care-executions", a,
                                     {"microcrystalId": mc, "connectionProof": "OTHER",
                                      "consentEvidenceRef": "consent-2", "planId": plan,
                                      "capture": {"captureId": "c2", "capturedAt": utcnow(),
                                                  "clientContinuityId": "cc-2",
                                                  "purpose": "admission"}}, key)
    conflict_ok = c_conf2 == 409 and ecode((c_conf2, b_conf)) == "IDEMPOTENCY_CONTENT_CONFLICT"
    cc07_ok = (c == 201 and c_nokey >= 400 and c_rep == 200 and c_rep2 == 200 and same
               and replayed and rev_before == rev_after and rev_before != "" and conflict_ok
               and bool(ex))
    _add("CC-07", "幂等与重放：缺键 4xx、同键重放 replayed 且 **verification_revision+"
                  "last_verified_at 均不刷新**、同键异内容 409",
         "PASS" if cc07_ok else "FAIL", "A03 重放/冲突", f"{c}/{c_rep}/{c_conf2}",
         f"nokey={c_nokey} same_exec={same} replayed={replayed} rev+last_verified {rev_before}->"
         f"{rev_after} conflict={conflict_ok} reason={ecode((c_conf2, b_conf))}")

    # ================= CC-08 占用/并发/释放/TASK_REPLACED =================
    plan2, mc2 = new_plan_and_mc(target=3)
    gtok = ctx["gtok"]
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(post_multipart, f"{CARE}/care-executions", a,
                         mk_metadata(mc2, plan=plan2), str(uuid.uuid4()))
        f2 = pool.submit(post_multipart, f"{CARE}/care-executions", gtok,
                         mk_metadata(mc2, task=ctx["assessment"], rev="1"), str(uuid.uuid4()))
        r1, r2 = f1.result(), f2.result()
    codes = sorted([r1[0], r2[0]])
    resp409 = r1 if r1[0] == 409 else r2
    concurrency_ok = codes == [201, 409] and ecode(resp409) == "DEVICE_OCCUPIED"
    # 释放并发成功者（否则其 gimbal 槽位会阻塞后续 TASK_REPLACED 用的云台准入）
    win_resp = r1 if r1[0] == 201 else r2
    win_tok = a if r1[0] == 201 else gtok
    ex_c = (win_resp[1].get("data") or {}).get("executionId")
    ep_c = (win_resp[1].get("data") or {}).get("recordStreamEpoch") or ex_c
    if ex_c:
        sync(win_tok, ex_c, obs_records(ep_c, [], seq=1, state="stopped"), str(uuid.uuid4()))
        closure(win_tok, ex_c, ep_c, 0, 0, str(uuid.uuid4()), stop_seq=1)
    # 占用仅 closed 释放
    mc_r = seed_microcrystal()
    pr1 = on_mc(mc_r)
    cr1, br1 = admit(a, mc_r, pr1, key=str(uuid.uuid4()))
    ex_r = (br1.get("data") or {}).get("executionId")
    ep_r = (br1.get("data") or {}).get("recordStreamEpoch") or ex_r
    pr2 = on_mc(mc_r)
    cr2, br2 = admit(a, mc_r, pr2, key=str(uuid.uuid4()))
    occ_before = cr2 == 409 and ecode((cr2, br2)) == "DEVICE_OCCUPIED"
    sobs(ex_r, ep_r, 1, "stopped")
    cl_r = closure(a, ex_r, ep_r, 0, 0, str(uuid.uuid4()), stop_seq=1)
    closed_r = (cl_r[1].get("data") or {}).get("closed") is True
    pr3 = on_mc(mc_r)
    cr3, br3 = admit(a, mc_r, pr3, key=str(uuid.uuid4()))
    occ_after = cr3 == 201
    # TASK_REPLACED（test_seed：SQL 移动 T03 指针；D 真实链路保持 dependency_pending）
    orig_asmt = scalar(f"SELECT coalesce(current_assessment_id::text,'') FROM gimbals "
                       f"WHERE id='{ctx['gimbal']}'")
    orig_rev = scalar(f"SELECT current_assessment_revision FROM gimbals WHERE id='{ctx['gimbal']}'")
    asmt_g = seed_assessment(ctx["gimbal"], member)
    mc_g = seed_microcrystal()
    plan_g = seed_plan(asmt_g, member, "ready", target=3, mc=mc_g)
    sql(f"UPDATE gimbals SET current_assessment_id='{asmt_g}', current_assessment_revision=1,"
        f" updated_at=now() WHERE id='{ctx['gimbal']}'")
    cg, bg = post_multipart(f"{CARE}/care-executions", gtok,
                            mk_metadata(mc_g, task=asmt_g, rev="1"), str(uuid.uuid4()))
    ex_g = (bg.get("data") or {}).get("executionId")
    asmt_g2 = seed_assessment(ctx["gimbal"], member)
    sql(f"UPDATE gimbals SET current_assessment_id='{asmt_g2}', current_assessment_revision=2,"
        f" updated_at=now() WHERE id='{ctx['gimbal']}'")
    ct, bt = post_multipart(f"{CARE}/care-executions", gtok,
                            mk_metadata(mc_g, task=asmt_g, rev="1"), str(uuid.uuid4()))
    A08t = get_json(f"{CARE}/care-plans/{plan_g}/progress?executionId={ex_g}"
                    f"&verificationRevision=1", gtok)
    replaced_a03 = ct == 409 and ecode((ct, bt)) == "TASK_REPLACED"
    replaced_a08 = A08t[0] == 409 and ecode(A08t) == "TASK_REPLACED"
    sql(f"UPDATE gimbals SET current_assessment_id='{orig_asmt}',"
        f" current_assessment_revision={orig_rev or 0}, updated_at=now() "
        f"WHERE id='{ctx['gimbal']}'")
    cc08_ok = (concurrency_ok and occ_before and closed_r and occ_after
               and replaced_a03 and replaced_a08)
    _add("CC-08", "占用/并发：APP+云台同微晶恰一 201 一 409 DEVICE_OCCUPIED；占用仅 closed "
                  "释放（closed 前 409 / closed 后 201）；旧任务 A03/A08 → 409 TASK_REPLACED",
         "PASS" if cc08_ok else "FAIL", "并发 + 启停 + SQL 移动 T03 指针（test_seed）",
         f"{codes}",
         f"app/gimbal={r1[0]}/{r2[0]} code409={ecode(resp409)} occ_before={occ_before} "
         f"closed_release={closed_r} occ_after={occ_after} replaced_a03={replaced_a03} "
         f"replaced_a08={replaced_a08}({ecode(A08t)})")

    # ================= CC-09 账本去重/K/状态机/冲突/溢出/迟到 =================
    plan_k, mc_k = new_plan_and_mc(target=10)
    ck, bk = admit(a, mc_k, plan_k, key=str(uuid.uuid4()))
    ex_k = (bk.get("data") or {}).get("executionId")
    ep_k = (bk.get("data") or {}).get("recordStreamEpoch") or ex_k
    if not ex_k:
        _add("CC-09", "账本去重/K/事务/状态机/迟到", "FAIL", "A03 for ledger scenario", ck,
             f"A03 failed: {str(bk)[:300]}")
        _add("CC-10", "收尾对账", "FAIL", "A03 for closure scenario", ck, f"{str(bk)[:200]}")
        return plan_k, None
    clo_un = closure(a, ex_k, ep_k, 0, 0, str(uuid.uuid4()), stop_seq=1)
    # duplicate：首批 2 条 HTTP 200；**逐字节相同记录**新键重放 disposition 全 duplicate（非空）
    ts0 = utcnow()
    dup_recs = [{"recordId": "dup-1", "sourceEpoch": ep_k, "sourceSeq": "1",
                 "countDelta": "1", "occurredAt": ts0},
                {"recordId": "dup-2", "sourceEpoch": ep_k, "sourceSeq": "2",
                 "countDelta": "1", "occurredAt": ts0}]
    s1 = srec(ex_k, ep_k, dup_recs)
    s2 = srec(ex_k, ep_k, dup_recs)
    disp2 = [(r.get("disposition")) for r in
             (s2[1].get("data") or {}).get("acknowledgedRecords", [])]
    dup_ok = (s1[0] == 200 and s2[0] == 200 and disp2 == ["duplicate", "duplicate"]
              and acc_of(ex_k) == "2")
    # K=9/10/11：completed_at 首达 10 即置、11 不改写、K 不截断
    for seq in range(3, 10):
        srec(ex_k, ep_k, [rec(ep_k, seq)])
    k9_ok = acc_of(ex_k) == "9" and comp_plan(plan_k) == ""
    srec(ex_k, ep_k, [rec(ep_k, 10)])
    acc10, comp10 = acc_of(ex_k), comp_plan(plan_k)
    k10_ok = acc10 == "10" and comp10 != ""
    srec(ex_k, ep_k, [rec(ep_k, 11)])
    acc11, comp11 = acc_of(ex_k), comp_plan(plan_k)
    k11_ok = acc11 == "11" and comp11 == comp10 and comp10 != ""
    # 状态机：连续性失效→不 running；unknown；unknown 拒绝 →running
    sobs(ex_k, ep_k, 1, "running", continuity=False)
    st_inv = status_of(ex_k)
    sobs(ex_k, ep_k, 2, "unknown")
    st_unknown = status_of(ex_k)
    sobs(ex_k, ep_k, 3, "running")
    st_run_from_unknown = status_of(ex_k)
    gating_ok = (st_inv == "admitted" and st_unknown == "unknown"
                 and st_run_from_unknown == "unknown")
    # 同记录键（sourceSeq）异内容、不同幂等键 → 409 RECORD_CONFLICT + 零持久化
    k1, k2 = str(uuid.uuid4()), str(uuid.uuid4())
    s4 = srec(ex_k, ep_k, [rec(ep_k, 12, rid="conf-a")], k1)
    s5 = srec(ex_k, ep_k, [rec(ep_k, 12, delta="2", rid="conf-b")], k2)
    rows_x = scalar(f"SELECT count(*) FROM care_records WHERE execution_id='{ex_k}'"
                    " AND client_record_id='conf-b'")
    conflict_ok2 = (s4[0] == 200 and s5[0] == 409 and ecode(s5) == "RECORD_CONFLICT"
                    and rows_x == "0")
    # stopped 冻结前水位：obs seq=4 stopped
    sobs(ex_k, ep_k, 4, "stopped")
    st_stopped = status_of(ex_k)
    # 溢出：plan.completed_count=MAX 后增量 1 → 400 count_overflow
    plan_o, mc_o = new_plan_and_mc(target=10)
    co, bo = admit(a, mc_o, plan_o, key=str(uuid.uuid4()))
    ex_o = (bo.get("data") or {}).get("executionId")
    ep_o = (bo.get("data") or {}).get("recordStreamEpoch") or ex_o
    sql(f"UPDATE care_plans SET completed_count=9223372036854775807 WHERE id='{plan_o}'")
    s_o = srec(ex_o, ep_o, [rec(ep_o, 1)])
    overflow_ok = s_o[0] == 400 and ecode(s_o) == "INVALID_INPUT" and ereason(s_o) == "count_overflow"
    cc09_ok = cc09_verdict(dup_ok=dup_ok, k9_ok=k9_ok, k10_ok=k10_ok, k11_ok=k11_ok,
                           gating_ok=gating_ok, conflict_ok=conflict_ok2,
                           stopped_ok=(st_stopped == "stopped"), overflow_ok=overflow_ok)
    _add("CC-09", "账本去重/K/事务/状态机：duplicate 非空==2、首批 200、K=9/10/11 边界"
                  "（completed_at 首达/不改写/K 不截断）、running 门控+unknown 拒绝、"
                  "同键异内容 409 零持久化、溢出 400 count_overflow",
         "PASS" if cc09_ok else "FAIL", "A05 多批 + SQL 核对", f"{s1[0]}/{s2[0]}/{s5[0]}",
         f"dup={disp2}(acc {acc_of(ex_k)}) k9={k9_ok} "
         f"K10={acc10}/{bool(comp10)} K11={acc11}/stable={comp11 == comp10} "
         f"gating={gating_ok}({st_inv}/{st_unknown}/{st_run_from_unknown}) "
         f"conflict={conflict_ok2}({s4[0]}/{s5[0]}/{ecode(s5)}/{rows_x}) "
         f"stopped={st_stopped} overflow={s_o[0]}/{ereason(s_o)}")

    # ================= CC-10 收尾对账 =================
    # 缺口：stopped + finalRecordSeq 超实际 → 409 CLOSURE_GAPS + 有界 missingRanges/more
    gaps = closure(a, ex_k, ep_k, 99, 12, str(uuid.uuid4()), stop_seq=4)
    gdet = (gaps[1].get("error") or {}).get("details") or {}
    gaps_ok = (gaps[0] == 409 and ecode(gaps) == "CLOSURE_GAPS" and gdet.get("reason") == "gaps"
               and isinstance(gdet.get("missingRanges"), list)
               and len(gdet.get("missingRanges") or []) <= 20
               and isinstance(gdet.get("more"), bool))
    # 并发双收尾恰一成功（不同键）
    kb, kc = str(uuid.uuid4()), str(uuid.uuid4())
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        fb = pool.submit(closure, a, ex_k, ep_k, 12, 12, kb, 4)
        fc = pool.submit(closure, a, ex_k, ep_k, 12, 12, kc, 4)
        rb, rcv = fb.result(), fc.result()
    pair = sorted([rb[0], rcv[0]])
    winner = rb if rb[0] == 200 else rcv
    win_key = kb if rb[0] == 200 else kc
    closed = (winner[1].get("data") or {}).get("closed") is True
    occ_rel = (winner[1].get("data") or {}).get("occupancyReleased") is True
    one_ok = pair == [200, 409]
    # 同一收尾键重放：2xx 且 manifest 逐字节不变
    manifest_before = scalar(f"SELECT closure_manifest::text FROM care_executions WHERE id='{ex_k}'")
    rep = closure(a, ex_k, ep_k, 12, 12, win_key, 4)
    manifest_after = scalar(f"SELECT closure_manifest::text FROM care_executions WHERE id='{ex_k}'")
    replay_ok = rep[0] == 200 and manifest_after == manifest_before and bool(manifest_before)
    # closed 冻结：更高序号观察被忽略，状态不变
    sobs(ex_k, ep_k, 5, "running")
    freeze_ok = status_of(ex_k) == "closed"
    # closed 后迟到记录入账 + late_variance 留痕 + 不重开
    s_late = srec(ex_k, ep_k, [rec(ep_k, 13)])
    late_cnt = scalar("SELECT coalesce(closure_manifest->'late_variance'->>'late_records_count','') "
                      f"FROM care_executions WHERE id='{ex_k}'")
    late_ok = s_late[0] == 200 and status_of(ex_k) == "closed" and late_cnt == "1"
    # 撤销后：A05 最小 ack(progress=null) + A06 仍可收尾 + A07 最小视图
    plan_rv, mc_rv = new_plan_and_mc(target=3)
    crv, brv = admit(a, mc_rv, plan_rv, key=str(uuid.uuid4()))
    ex_rv = (brv.get("data") or {}).get("executionId")
    ep_rv = (brv.get("data") or {}).get("recordStreamEpoch") or ex_rv
    sql(f"UPDATE member_access_grants SET status='revoked', revoked_at=now(), updated_at=now() "
        f"WHERE account_id='{ctx['accountId']}' AND member_id='{member}'")
    s_rev = sobs(ex_rv, ep_rv, 1, "stopped")
    ack_ok = s_rev[0] == 200 and (s_rev[1].get("data") or {}).get("progress") is None
    cl_rev = closure(a, ex_rv, ep_rv, 0, 0, str(uuid.uuid4()), stop_seq=1)
    still_close = cl_rev[0] == 200 and (cl_rev[1].get("data") or {}).get("closed") is True
    A07r = get_json(f"{CARE}/care-executions/{ex_rv}", a)
    d7r = A07r[1].get("data") or {}
    minimal = (A07r[0] == 200 and d7r.get("memberId") is None and d7r.get("planId") is None
               and d7r.get("progress") is None and d7r.get("controller") is None)
    sql(f"UPDATE member_access_grants SET status='active', revoked_at=NULL, updated_at=now() "
        f"WHERE account_id='{ctx['accountId']}' AND member_id='{member}'")
    A07 = get_json(f"{CARE}/care-executions/{ex_k}", a)
    A08 = get_json(f"{CARE}/care-plans/{plan_k}/progress", a)
    A09 = get_json(f"{CARE}/members/{member}/care-executions", a)
    cc10_ok = cc10_verdict(
        stop_ok=(clo_un[0] == 409 and ecode(clo_un) == "STOP_NOT_CONFIRMED"), gaps_ok=gaps_ok,
        one_ok=one_ok, closed=closed, occ_rel=occ_rel, replay_ok=replay_ok, freeze_ok=freeze_ok,
        late_ok=late_ok, ack_ok=ack_ok, still_close=still_close, minimal=minimal,
        get_2xx=(A07[0] == 200 and A08[0] == 200 and A09[0] == 200))
    _add("CC-10", "收尾对账：未 stopped 409 STOP_NOT_CONFIRMED；缺口 409 CLOSURE_GAPS+有界"
                  "missingRanges/more；水位完整→closed+occupancyReleased；并发双收尾恰一成功；"
                  "同键重放 manifest 逐字节不变；closed 冻结+迟到入账 late_variance 不重开；"
                  "撤销后 A05 最小 ack(progress=null)+A06 仍可收尾+A07 最小视图；A07/08/09 2xx",
         "PASS" if cc10_ok else "FAIL", "A06 前后置 + 并发/重放/迟到/撤销（test_seed）",
         f"{clo_un[0]}/{gaps[0]}/{winner[0]}",
         f"stop_err={ecode(clo_un)} gaps={gaps_ok}({len(gdet.get('missingRanges') or [])},"
         f"more={gdet.get('more')}) pair={pair} closed={closed} released={occ_rel} "
         f"manifest_stable={manifest_after == manifest_before} freeze={freeze_ok} "
         f"late={late_ok}(cnt={late_cnt}) ack={ack_ok} close_after_revoke={still_close} "
         f"minimal={minimal} A07/08/09={A07[0]}/{A08[0]}/{A09[0]}")
    return plan_k, ex_k



# ---------------- CC-11/12 ----------------

def cc_11(ctx):
    from driver import a_reverify as AR
    a, member = ctx["tok"], ctx["member"]
    st = I.run([str(I.PY), str(AR.VALIDATE), "--selftest"], cwd=I.CONTRACTS, timeout=180,
               log_name="cc-11-selftest.log")
    samp = I.run([str(I.PY), "scripts/validate_samples.py"], cwd=I.CONTRACTS, timeout=180,
                 log_name="cc-11-samples.log")
    n = re.search(r"(\d+)\s+checks", samp.stdout)
    oas = I.run([str(I.PY), "-c", "import yaml\nfrom openapi_spec_validator import validate\n"
                 "validate(yaml.safe_load(open('openapi/openapi.yaml')))\nprint('OPENAPI VALID')"],
                cwd=I.CONTRACTS, timeout=180, log_name="cc-11-openapi.log")
    baseline_ok = (st.returncode == 0 and "10 checks passed" in st.stdout and samp.returncode == 0
                   and n and n.group(1) == "50" and oas.returncode == 0
                   and "OPENAPI VALID" in oas.stdout)
    # 9 个 M4 API 代表性成功响应：真实跑一遍生命周期并逐个严格 OAS schema 校验
    plan, mc = new_plan_and_mc(target=3)
    c3, b3 = admit(a, mc, plan, key=str(uuid.uuid4()))
    ex = (b3.get("data") or {}).get("executionId")
    ep = (b3.get("data") or {}).get("recordStreamEpoch") or ex
    caps = [("A03", "/api/v1/care-executions", "post", c3, b3)]
    if ex:
        c5, b5, _ = sync(a, ex, obs_records(ep, [], seq=1, state="paused"), str(uuid.uuid4()))
        rev = scalar(f"SELECT verification_revision FROM care_executions WHERE id='{ex}'")
        c4, b4 = post_multipart(f"{CARE}/care-executions/{ex}/revalidations", a,
                                {"expectedVerificationRevision": rev or "1",
                                 "capture": {"captureId": str(uuid.uuid4()), "capturedAt": utcnow(),
                                             "clientContinuityId": "cc-1", "purpose": "revalidation"},
                                 "consentEvidenceRef": "consent-1"}, str(uuid.uuid4()))
        c5b, b5b, _ = sync(a, ex, obs_records(ep, [rec(ep, 1)], seq=2, state="running"),
                           str(uuid.uuid4()))
        sync(a, ex, obs_records(ep, [], seq=3, state="stopped"), str(uuid.uuid4()))
        c6, b6, _ = closure(a, ex, ep, 1, 1, str(uuid.uuid4()), stop_seq=3)
        caps += [("A05", "/api/v1/care-executions/{executionId}/observations", "post", c5b, b5b),
                 ("A04", "/api/v1/care-executions/{executionId}/revalidations", "post", c4, b4),
                 ("A06", "/api/v1/care-executions/{executionId}/closure-confirmations", "post", c6, b6)]
    c1, b1, _ = get_json(f"{CARE}/members/{member}/care-plans", a)
    c2, b2, _ = get_json(f"{CARE}/care-plans/{plan}?view=full", a)
    c7, b7, _ = get_json(f"{CARE}/care-executions/{ex}", a)
    c8, b8, _ = get_json(f"{CARE}/care-plans/{plan}/progress", a)
    c9, b9, _ = get_json(f"{CARE}/members/{member}/care-executions", a)
    caps += [("A01", "/api/v1/members/{memberId}/care-plans", "get", c1, b1),
             ("A02", "/api/v1/care-plans/{planId}", "get", c2, b2),
             ("A07", "/api/v1/care-executions/{executionId}", "get", c7, b7),
             ("A08", "/api/v1/care-plans/{planId}/progress", "get", c8, b8),
             ("A09", "/api/v1/members/{memberId}/care-executions", "get", c9, b9)]
    expected_status = {"A03": (201,), "A01": (200,), "A02": (200,), "A04": (200,),
                       "A05": (200,), "A06": (200,), "A07": (200,), "A08": (200,),
                       "A09": (200,)}
    status_bad, impl_bad, contract_issues = [], [], []
    captured, actual_status = {}, {}
    for api, path, method, actual, body in caps:
        captured[api] = {"status": actual, "body": body}
        actual_status[api] = actual
        if actual not in expected_status[api]:
            status_bad.append(f"{api}={actual} not in {expected_status[api]}")
            continue
        for e in oas_errors_path(path, method, actual, body):
            kind = classify_strict_error(api, e)
            issue = f"{api} {normalize_json_path(e.json_path)} [{kind}]"
            (contract_issues if kind.startswith("contract") else impl_bad).append(issue)
    I.evidence_text("cc-11-captured.json", json.dumps(captured, ensure_ascii=False, indent=2))
    status = cc11_outcome(baseline_ok, len(caps), status_bad, impl_bad, contract_issues)
    _add("CC-11", "有界严格契约：selftest 10/10 + samples 50 + OpenAPI VALID；9 个 M4 API"
                  "（A01-A09）按**实际 HTTP 状态**对应 schema 严格校验（RV-6 转换器，不改 OAS "
                  "语义、不展平 allOf）；契约建模问题如实披露、绝不静默放宽",
         status, "契约脚本 + 真实生命周期捕获 9 响应（实际状态）严格校验",
         f"{st.returncode}/{samp.returncode}/{oas.returncode}",
         f"selftest={st.returncode == 0} samples={n.group(1) if n else '?'} "
         f"oas_ok={oas.returncode == 0} captured={len(caps)} actual_status={actual_status} "
         f"status_bad={status_bad} impl_bad={impl_bad[:4]} contract_issues={contract_issues[:8]}")


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
                                                target=3, mc=mc, summary=SENSITIVE_SUMMARY)
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
                        cc_11(CONTEXT)
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
