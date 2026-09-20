# -*- coding: utf-8 -*-
"""SC-01 · 配网、账号绑定、心跳与通知 —— 集成轮 batch 1 真实步骤（18 节点）。

gate=open：后端可自动节点真实执行 HTTP + SQL 断言并结算 passed/failed；
联调（设备APP）节点执行后端侧可先验子步骤后，以 dependency_pending 结算
（真实设备/APP 联调仍待办，绝不冒充 real_pass）。
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

M = "SC-01"
P = {i: pytest.mark.priority for i in ()}  # 占位，避免误用


def _mark(sid: str, prio: str, scope: str, pkgs: list[str], deps: list[str]):
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
    se.record_raw(method=method, path=path, status=code,
                  request_id="", request_headers=headers or {}, request_json=req,
                  response_excerpt=json.dumps(body, ensure_ascii=False)[:4000],
                  started_at=0.0, elapsed_ms=0.0)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed_bound_gimbal() -> tuple[str, str | None]:
    g = CC.seed_gimbal()
    return g, CC.gimbal_token(g)


def _status(sess) -> tuple[str, int]:
    """建立一个已绑定云台：返回 (gimbalId, bindingRevision)。"""
    g = CC.seed_gimbal()
    proof = live.pairing_proof(g, sess["accountId"], sess["installationId"])
    code, body, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}",
                           token=sess["access"], body={
                               "expectedBindingRevision": "0", "pairingProof": proof},
                           headers={"Idempotency-Key": str(uuid.uuid4())})
    assert code == 200, (code, body)
    return g, int((body.get("data") or {}).get("bindingRevision", "0"))


# ---------------- 后端可自动（真实 HTTP） ----------------

@_mark("SC-01-03", "P0", "后端", ["B"], ["D01"])
def test_SC_01_03(scenario_evidence):
    """未登录直接请求绑定/登记通知目标：401 且不产生任何写入。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "配对证明 dev 替身")
    g = CC.seed_gimbal()
    c1, b1, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", body={
        "expectedBindingRevision": "0", "pairingProof": "x"})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", c1, b1)
    c2, b2, _ = I.http("PUT", "/api/v1/me/notification-destinations/inst-x",
                       body={"provider": "p", "platform": "android", "registration": {},
                             "expectedDestinationRevision": "0"})
    _rec(se, "PUT", "/api/v1/me/notification-destinations/inst-x", c2, b2)
    c3, b3, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token="forged",
                       body={"expectedBindingRevision": "0", "pairingProof": "x"})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", c3, b3, headers={"Authorization": "Bearer forged"})
    rows = CC.scalar(f"SELECT count(*) FROM gimbals WHERE id='{g}' AND bound_account_id IS NOT NULL")
    dest = CC.scalar("SELECT count(*) FROM notification_destinations WHERE installation_id='inst-x'")
    assert c1 == 401 and b1["error"]["code"] == "AUTH_REQUIRED"
    assert c2 == 401 and b2["error"]["code"] == "AUTH_REQUIRED"
    assert c3 == 401 and b3["error"]["code"] == "SESSION_INVALID"
    assert rows == "0" and dest == "0"
    se.seal()


@_mark("SC-01-04", "P0", "后端", ["B"], ["D01"])
def test_SC_01_04(scenario_evidence):
    """重复绑定同一账号：返回 self 且不产生重复关系/不递增代次。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "配对证明 dev 替身")
    sess = live.app_login("sc0104")
    g, rev = _status(sess)
    # 同账号同代次重复绑定（新幂等键）
    proof = live.pairing_proof(g, sess["accountId"], sess["installationId"])
    c, b, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=sess["access"],
                     body={"expectedBindingRevision": str(rev), "pairingProof": proof},
                     headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", c, b)
    data = b.get("data") or {}
    row = CC.scalar("SELECT count(*)||'|'||max(binding_revision) FROM gimbals "
                    f"WHERE id='{g}'")
    assert c == 200 and data.get("bindingStatus") == "self"
    assert int(data.get("bindingRevision")) == rev
    assert row == f"1|{rev}", row
    se.seal()


@_mark("SC-01-05", "P0", "后端", ["B"], ["D01"])
def test_SC_01_05(scenario_evidence):
    """绑定已属其他账号的云台：409 BOUND_TO_OTHER，原绑定保持。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "配对证明 dev 替身")
    a = live.app_login("sc0105a")
    b = live.app_login("sc0105b")
    g, rev = _status(a)
    proof = live.pairing_proof(g, b["accountId"], b["installationId"])
    cb, bb, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=b["access"],
                       body={"expectedBindingRevision": str(rev), "pairingProof": proof},
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", cb, bb)
    owner = CC.scalar(f"SELECT bound_account_id FROM gimbals WHERE id='{g}'")
    assert cb == 409 and bb["error"]["code"] == "BOUND_TO_OTHER"
    assert owner == a["accountId"], owner
    se.seal()


@_mark("SC-01-06", "P0", "后端", ["B"], ["D01"])
def test_SC_01_06(scenario_evidence):
    """绑定凭据无效/伪造证明：拒绝，不能凭任意 ID 建立访问关系。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "配对证明 dev 替身")
    sess = live.app_login("sc0106")
    g = CC.seed_gimbal()
    # 恶意签名（把签名段替换掉）
    good = live.pairing_proof(g, sess["accountId"], sess["installationId"])
    bad_sig = good.rsplit(".", 1)[0] + ".AAAA"
    c1, b1, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=sess["access"],
                       body={"expectedBindingRevision": "0", "pairingProof": bad_sig},
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", c1, b1)
    c2, b2, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=sess["access"],
                       body={"expectedBindingRevision": "0", "pairingProof": "not-a-proof"},
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", c2, b2)
    bound = CC.scalar(f"SELECT count(*) FROM gimbals WHERE id='{g}' AND bound_account_id IS NOT NULL")
    assert c1 == 403 and b1["error"]["code"] == "CALLER_NOT_ALLOWED"
    assert c2 == 400 and b2["error"]["code"] == "INVALID_INPUT"
    assert bound == "0"
    se.seal()


@_mark("SC-01-09", "P0", "后端", ["B"], ["D01"])
def test_SC_01_09(scenario_evidence):
    """云台认证成功与凭据失败：合法签发上下文，失败不建护理执行。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "设备凭据 dev 替身")
    g = CC.seed_gimbal()
    c1, b1, _ = live.gimbal_session(g)
    _rec(se, "POST", "/api/v1/gimbal-sessions", c1, b1)
    c2, b2, _ = I.http("POST", "/api/v1/gimbal-sessions", body={
        "credential": "wrong-credential", "credentialVersion": "1", "proof": "p"})
    _rec(se, "POST", "/api/v1/gimbal-sessions", c2, b2)
    tok = (b1.get("data") or {}).get("sessionToken")
    executions = CC.scalar("SELECT count(*) FROM care_executions")
    assert c1 == 200 and tok
    assert c2 in (401, 404)
    assert executions == "0"
    # 凭据版本推进 → 旧 token 立即 401
    CC.sql(f"UPDATE gimbals SET credential_version=credential_version+1 WHERE id='{g}'")
    c3, b3, _ = I.http("GET", f"/api/v1/gimbals/{g}/status", token=tok)
    _rec(se, "GET", f"/api/v1/gimbals/{g}/status", c3, b3)
    assert c3 == 401
    se.seal()


@_mark("SC-01-10", "P1", "后端", ["B"], ["D03", "D04"])
def test_SC_01_10(scenario_evidence):
    """心跳重复/迟到/旧上报：逐响应状态+accepted 语义；业务列（K/占用/执行状态/绑定）逐列前后全等；
    心跳信息列可更新但不得误改业务状态。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "心跳来源 dev 替身")
    se.doubles.add("face_algo", "double", "MemberBindingFaceDouble（dev 绑定成员）")
    # —— 真实前置态（真实链 M3→worker→T06 ready→A03 准入→A05 K=1→open 占用）——
    g, tk = live.gimbal_with_token()
    _c, _b = live.multipart_a01(tk, str(uuid.uuid4()))
    tid = (_b.get("data") or {}).get("taskId")
    assert _c == 202
    for _ in range(140):
        if CC.scalar(f"SELECT (status='report_ready')::int FROM skin_assessments WHERE id='{tid}'") == "1":
            break
        I.worker_once(timeout=180)
    mid = CC.scalar(f"SELECT member_id::text FROM skin_assessments WHERE id='{tid}'")
    plan = CC.scalar(f"SELECT id::text FROM care_plans WHERE assessment_id='{tid}'")
    obs = live.app_login("s0110o")
    serial = f"mc-{uuid.uuid4().hex[:8]}"
    live.observe_microcrystal(obs, serial, live.CAP_BASELINE)
    for _ in range(60):
        if CC.scalar(f"SELECT (generation_status='ready')::int FROM care_plans WHERE id='{plan}'") == "1":
            break
        I.worker_once(timeout=180)
    mc = CC.scalar(f"SELECT id::text FROM microcrystals WHERE serial_no='{serial}'")
    live.java_env_with_bound_member(mid)
    a = live.app_login("sc0110")
    CC.seed_grant(a["accountId"], mid, status="active")
    CC.sql(f"UPDATE gimbals SET bound_account_id='{a['accountId']}', binding_revision=1,"
           f" bound_at=now() WHERE id='{g}'")
    tok = CC.gimbal_token(g)
    code, body = CC.admit(a["access"], mc, plan, key=str(uuid.uuid4()))
    assert code == 201, (code, body)
    ex = (body.get("data") or {}).get("executionId")
    ep = (body.get("data") or {}).get("recordStreamEpoch") or ex
    rev = CC.scalar(f"SELECT verification_revision FROM care_executions WHERE id='{ex}'")
    cs, cb_, _ = CC.sync(a["access"], ex, CC.obs_records(ep, [CC.rec(ep, 1)], seq=1,
                                                         state="running", rev=rev), str(uuid.uuid4()))
    assert cs == 200 and CC.scalar(f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{plan}'") == "1"
    assert CC.scalar(f"SELECT count(*) FROM care_executions WHERE id='{ex}' AND closed_at IS NULL") == "1"
    def care():
        return "|".join(CC.scalar(s) for s in (
            f"SELECT coalesce(completed_count,0) FROM care_plans WHERE id='{plan}'",
            f"SELECT status FROM care_executions WHERE id='{ex}'",
            f"SELECT (closed_at IS NULL)::int FROM care_executions WHERE id='{ex}'",
            f"SELECT verification_revision FROM care_executions WHERE id='{ex}'",
            f"SELECT coalesce(bound_account_id::text,'') FROM gimbals WHERE id='{g}'"))
    def hb():
        return CC.scalar("SELECT last_seen_at::text||'|'||status_revision||'|'||connection_status "
                         f"FROM gimbals WHERE id='{g}'")
    care0, hb0 = care(), hb()
    e1 = f"ep-{uuid.uuid4().hex[:8]}"
    base = {"observationEpoch": e1, "observedAt": _now(), "powerState": "awake"}
    c1, b1, _ = I.http("POST", f"/api/v1/gimbals/{g}/heartbeats", token=tok,
                       body={**base, "observationSeq": "1"})
    _rec(se, "POST", f"/api/v1/gimbals/{g}/heartbeats", c1, b1, req={"seq": 1})
    # 重复 seq：精确拒绝语义
    c2, b2, _ = I.http("POST", f"/api/v1/gimbals/{g}/heartbeats", token=tok,
                       body={**base, "observationSeq": "1"})
    _rec(se, "POST", f"/api/v1/gimbals/{g}/heartbeats", c2, b2, req={"seq": 1, "dup": True})
    # 合法推进
    c3, b3, _ = I.http("POST", f"/api/v1/gimbals/{g}/heartbeats", token=tok,
                       body={**base, "observationSeq": "2"})
    _rec(se, "POST", f"/api/v1/gimbals/{g}/heartbeats", c3, b3, req={"seq": 2})
    hb1 = hb()
    # 真实迟到（旧 seq）+旧 observedAt
    old_ts = "2020-01-01T00:00:00Z"
    c4, b4, _ = I.http("POST", f"/api/v1/gimbals/{g}/heartbeats", token=tok,
                       body={**base, "observationSeq": "1", "observedAt": old_ts})
    _rec(se, "POST", f"/api/v1/gimbals/{g}/heartbeats", c4, b4, req={"late_seq": 1})
    c5, b5, _ = I.http("POST", f"/api/v1/gimbals/{g}/heartbeats", token=tok,
                       body={**base, "observationSeq": "2", "observedAt": old_ts})
    _rec(se, "POST", f"/api/v1/gimbals/{g}/heartbeats", c5, b5, req={"old_observed_at": old_ts})
    # B 心跳契约：新序号 200+accepted=true；旧序号/重复 200+accepted=false（仍确认收到）
    assert c1 == 200 and (b1.get("data") or {}).get("accepted") is True
    assert c3 == 200 and (b3.get("data") or {}).get("accepted") is True
    for cc_, bb_ in ((c2, b2), (c4, b4), (c5, b5)):
        assert cc_ == 200, (cc_, bb_)
        assert (bb_.get("data") or {}).get("accepted") is False, bb_
    assert care() == care0, (care0, care())      # 业务列（K/执行状态/占用/revision/绑定）全等
    assert hb() == hb1, (hb1, hb())              # 迟到不误改心跳信息列
    se.seal()


@_mark("SC-01-12", "P0", "后端", ["B"], ["D01"])
def test_SC_01_12(scenario_evidence):
    """云台状态查询的访问范围：绑定账号/云台自身可见，他人 404。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "设备 dev 替身")
    a = live.app_login("sc0112a")
    b = live.app_login("sc0112b")
    g, _rev = _status(a)
    tok = CC.gimbal_token(g)
    c_self, b_self, _ = I.http("GET", f"/api/v1/gimbals/{g}/status", token=tok)
    _rec(se, "GET", f"/api/v1/gimbals/{g}/status", c_self, b_self)
    c_a, b_a, _ = I.http("GET", f"/api/v1/gimbals/{g}/status", token=a["access"])
    _rec(se, "GET", f"/api/v1/gimbals/{g}/status", c_a, b_a)
    c_b, b_b, _ = I.http("GET", f"/api/v1/gimbals/{g}/status", token=b["access"])
    _rec(se, "GET", f"/api/v1/gimbals/{g}/status", c_b, b_b)
    assert c_self == 200 and c_a == 200
    assert c_b == 404 and b_b["error"]["code"] == "RESOURCE_NOT_VISIBLE"
    se.seal()


# ---------------- 设备APP（后端子步骤 + 真实联调待办） ----------------

def _device_done(se, substeps: int, total: int = 3):
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + gate.device_pending(substeps, total))


@_mark("SC-01-01", "P0", "联调", ["B"], ["D01", "D02"])
def test_SC_01_01(scenario_evidence):
    """后端可先验：status unbound→bind self→status self。真实按钮/UI 联调待办。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "配对证明 dev 替身")
    sess = live.app_login("sc0101")
    g = CC.seed_gimbal()
    proof = live.pairing_proof(g, sess["accountId"], sess["installationId"])
    cu, bu, _ = I.http("GET", f"/api/v1/gimbals/{g}/binding-status", token=sess["access"],
                       headers={"X-Pairing-Proof": proof})
    _rec(se, "GET", f"/api/v1/gimbals/{g}/binding-status", cu, bu, headers={"X-Pairing-Proof": "<redacted>"})
    proof_bind = live.pairing_proof(g, sess["accountId"], sess["installationId"])
    cb, bb, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=sess["access"],
                       body={"expectedBindingRevision": "0", "pairingProof": proof_bind},
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", cb, bb)
    proof2 = live.pairing_proof(g, sess["accountId"], sess["installationId"])
    cs, bs, _ = I.http("GET", f"/api/v1/gimbals/{g}/binding-status", token=sess["access"],
                       headers={"X-Pairing-Proof": proof2})
    _rec(se, "GET", f"/api/v1/gimbals/{g}/binding-status", cs, bs, headers={"X-Pairing-Proof": "<redacted>"})
    assert (bu.get("data") or {}).get("bindingStatus") == "unbound"
    assert cb == 200 and (bb.get("data") or {}).get("bindingStatus") == "self"
    assert (bs.get("data") or {}).get("bindingStatus") == "self"
    _device_done(se, 3)


@_mark("SC-01-02", "P0", "联调", ["B"], ["D01"])
def test_SC_01_02(scenario_evidence):
    """后端可先验：匿名/未登录不新建绑定与目标。真实配网联调待办。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "配对证明 dev 替身")
    g = CC.seed_gimbal()
    c1, b1, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", body={
        "expectedBindingRevision": "0", "pairingProof": "x"})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", c1, b1)
    c2, b2, _ = I.http("PUT", "/api/v1/me/notification-destinations/inst-anon", body={
        "provider": "p", "platform": "android", "registration": {},
        "expectedDestinationRevision": "0"})
    _rec(se, "PUT", "/api/v1/me/notification-destinations/inst-anon", c2, b2)
    bound = CC.scalar(f"SELECT count(*) FROM gimbals WHERE id='{g}' AND bound_account_id IS NOT NULL")
    dest = CC.scalar("SELECT count(*) FROM notification_destinations WHERE installation_id='inst-anon'")
    assert c1 == 401 and c2 == 401 and bound == "0" and dest == "0"
    _device_done(se, 2)


@_mark("SC-01-07", "P1", "联调", ["B"], ["D01"])
def test_SC_01_07(scenario_evidence):
    """后端可先验：绑定失败如实 409/404，不把联网成功等同绑定成功。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "配对证明 dev 替身")
    sess = live.app_login("sc0107")
    g = CC.seed_gimbal()
    bad = live.pairing_proof(g, sess["accountId"], sess["installationId"], ttl_s=-10)
    c, b, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=sess["access"],
                     body={"expectedBindingRevision": "0", "pairingProof": bad},
                     headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", c, b)
    bound = CC.scalar(f"SELECT count(*) FROM gimbals WHERE id='{g}' AND bound_account_id IS NOT NULL")
    assert c == 403 and bound == "0"
    _device_done(se, 1)


@_mark("SC-01-08", "P0", "联调", ["B"], ["D01", "D02"])
def test_SC_01_08(scenario_evidence):
    """后端可先验：匿名不替换原绑定；无绑定不发通知。真实匿名配网联调待办。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "配对证明 dev 替身")
    a = live.app_login("sc0108")
    g, rev = _status(a)
    c, b, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", body={
        "expectedBindingRevision": str(rev), "pairingProof": "x"})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", c, b)
    owner = CC.scalar(f"SELECT bound_account_id FROM gimbals WHERE id='{g}'")
    assert c == 401 and owner == a["accountId"]
    _device_done(se, 1)


@_mark("SC-01-11", "P1", "联调", ["B"], ["D03"])
def test_SC_01_11(scenario_evidence):
    """后端可先验：单次超时不置 offline；未知/过期可区分（isStale）。真实端侧联调待办。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "设备 dev 替身")
    sess = live.app_login("sc0111")
    g, _rev = _status(sess)
    c, b, _ = I.http("GET", f"/api/v1/gimbals/{g}/status", token=sess["access"])
    _rec(se, "GET", f"/api/v1/gimbals/{g}/status", c, b)
    data = b.get("data") or {}
    conn = CC.scalar(f"SELECT connection_status FROM gimbals WHERE id='{g}'")
    assert c == 200 and data.get("isStale") is True and conn != "offline"
    _device_done(se, 1)


@_mark("SC-01-13", "P0", "联调", ["B"], ["D05"])
def test_SC_01_13(scenario_evidence):
    """后端可先验：重连认证+补传心跳不自动新建/恢复护理执行。真实重连联调待办。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "设备 dev 替身")
    g, _rev = _seed_bound_gimbal()
    before = CC.scalar("SELECT count(*) FROM care_executions")
    tok = CC.gimbal_token(g)
    c, b, _ = I.http("POST", f"/api/v1/gimbals/{g}/heartbeats", token=tok,
                     body={"observationEpoch": f"re-{uuid.uuid4().hex[:6]}",
                           "observationSeq": "1", "observedAt": _now(), "powerState": "awake"})
    _rec(se, "POST", f"/api/v1/gimbals/{g}/heartbeats", c, b)
    after = CC.scalar("SELECT count(*) FROM care_executions")
    assert c == 200 and before == after
    _device_done(se, 2)


@_mark("SC-01-14", "P1", "联调", ["B"], ["D02"])
def test_SC_01_14(scenario_evidence):
    """后端可先验：登记通知目标成功且不回传 token；真实推送联调待办。"""
    se = scenario_evidence
    se.doubles.add("push_channel", "double", "推送通道 dev 替身")
    sess = live.app_login("sc0114")
    c, b, _ = I.http("PUT", f"/api/v1/me/notification-destinations/{sess['installationId']}",
                     token=sess["access"], body={
                         "provider": "dev", "platform": "android",
                         "registration": {"token": "SECRET-TOKEN"},
                         "expectedDestinationRevision": "0"},
                     headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/notification-destinations/{sess['installationId']}", c, b)
    data = b.get("data") or {}
    assert c in (200, 201) and "SECRET-TOKEN" not in json.dumps(b)
    assert data.get("destinationRevision") is not None
    _device_done(se, 1)


@_mark("SC-01-15", "P0", "联调", ["B"], ["D02", "D03"])
def test_SC_01_15(scenario_evidence):
    """后端可先验：**常驻 worker 周期自动触发**离线 episode；无绑定不建通知。真实推送联调待办。

    C8 已接线：run_forever 进程内 incident.scan + media.cleanup.discover 周期任务
    （env 短周期），**无 CLI 调用**；错过周期合并/start-to-start 语义见 scheduler.py。
    """
    se = scenario_evidence
    se.doubles.add("push_channel", "double", "推送通道 dev 替身")
    se.doubles.add("gimbal_device", "double", "设备 dev 替身")
    CC.sql("UPDATE gimbals SET last_seen_at = now() - interval '1 hour',"
           " connection_status='online' WHERE bound_account_id IS NULL")
    env = {"MVP_NOTIFY_OFFLINE_THRESHOLD_SECONDS": "1",
           "MVP_WORKER_INCIDENT_SCAN_INTERVAL_SECONDS": "2",
           "MVP_WORKER_MEDIA_CLEANUP_SCAN_INTERVAL_SECONDS": "2",
           "MVP_WORKER_POLL_INTERVAL_SECONDS": "1"}
    live.start_resident_worker(env)
    try:
        time.sleep(6)  # 至少两个 incident 周期（无绑定 → 无通知）
        notif_unbound = CC.scalar("SELECT count(*) FROM notifications")
        media_ran = live.resident_log_has("media.cleanup.discover")
        se.record_raw(method="OBSERVE", path="resident-worker 周期自动触发", status=0,
                      request_headers={}, request_json={"env": env},
                      response_excerpt=(f"notifications={notif_unbound} "
                                        f"media_cleanup_task_ran={media_ran} "
                                        f"incident_task_ran={live.resident_log_has('incident.scan')}"),
                      started_at=0.0, elapsed_ms=0.0)
        assert notif_unbound == "0", notif_unbound
        assert live.resident_log_has("incident.scan"), "incident.scan 周期任务未运行"
        assert media_ran, "media.cleanup.discover 周期任务未运行（C8 接线）"
    finally:
        live.stop_resident_worker()
    _device_done(se, 2)


@_mark("SC-01-16", "P1", "联调", ["B"], ["D02", "D03"])
def test_SC_01_16(scenario_evidence):
    """后端可先验：**常驻周期自动**触发后重复提醒按唯一键抑制、不误发。真实推送联调待办。"""
    se = scenario_evidence
    se.doubles.add("push_channel", "double", "推送通道 dev 替身")
    se.doubles.add("gimbal_device", "double", "设备 dev 替身")
    sess = live.app_login("sc0116")
    g, _rev = _status(sess)
    CC.sql(f"UPDATE gimbals SET last_seen_at = now() - interval '1 hour',"
           f" connection_status='online' WHERE id='{g}'")
    I.http("PUT", f"/api/v1/me/notification-destinations/{sess['installationId']}",
           token=sess["access"], body={"provider": "dev", "platform": "android",
                                       "registration": {"pushToken": "dev-token"},
                                       "expectedDestinationRevision": "0"},
           headers={"Idempotency-Key": str(uuid.uuid4())})
    env = {"MVP_NOTIFY_OFFLINE_THRESHOLD_SECONDS": "1",
           "MVP_WORKER_INCIDENT_SCAN_INTERVAL_SECONDS": "2",
           "MVP_WORKER_MEDIA_CLEANUP_SCAN_INTERVAL_SECONDS": "2",
           "MVP_WORKER_POLL_INTERVAL_SECONDS": "1"}
    live.start_resident_worker(env)
    try:
        assert live.wait_cond("SELECT (count(*)>=1)::int FROM notifications", 30), "周期未产生通知"
        mid = CC.scalar("SELECT count(*) FROM notifications")
        time.sleep(6)  # 多个后续周期：重复 episode 不应重复建行
        after = CC.scalar("SELECT count(*) FROM notifications")
        se.record_raw(method="OBSERVE", path="resident-worker 周期重复抑制", status=0,
                      request_headers={}, request_json={"env": env},
                      response_excerpt=f"notifications mid={mid} after={after}", started_at=0.0, elapsed_ms=0.0)
        assert after == mid, (mid, after)
    finally:
        live.stop_resident_worker()
    _device_done(se, 3)


@_mark("SC-01-17", "P0", "联调", ["B"], ["D02"])
def test_SC_01_17(scenario_evidence):
    """登出后旧账号目标失效 + destination_revision 同事务 +1（#8 已修实测）。"""
    se = scenario_evidence
    se.doubles.add("push_channel", "double", "推送通道 dev 替身")
    sess = live.app_login("sc0117")
    inst = sess["installationId"]
    cp, bp, _ = I.http("PUT", f"/api/v1/me/notification-destinations/{inst}", token=sess["access"],
                       body={"provider": "dev", "platform": "android",
                             "registration": {"pushToken": "dev-token"},
                             "expectedDestinationRevision": "0"},
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/notification-destinations/{inst}", cp, bp)
    assert cp in (200, 201), (cp, bp)
    rev0 = CC.scalar(f"SELECT destination_revision FROM notification_destinations "
                     f"WHERE installation_id='{inst}'")
    c, b, _ = I.http("DELETE", "/api/v1/auth/sessions/current", token=sess["access"])
    _rec(se, "DELETE", "/api/v1/auth/sessions/current", c, b)
    assert c in (200, 204)
    if c == 204:
        assert ("_raw" not in b) or (b.get("_raw") == ""), f"204 须真空体：{b}"
    else:
        assert b.get("requestId") and b.get("data") is not None and "error" not in b, b
    row = CC.scalar("SELECT status||'|'||destination_revision::text||'|'||"
                    f"coalesce(invalidated_at::text,'') FROM notification_destinations "
                    f"WHERE installation_id='{inst}'")
    _rec(se, "SQL", "logout T09 invalidate + revision+1", 0, {"row": row})
    # 重复登出幂等：revision / invalidated_at 不变
    c2, b2, _ = I.http("DELETE", "/api/v1/auth/sessions/current", token=sess["access"])
    _rec(se, "DELETE", "/api/v1/auth/sessions/current", c2, b2, req={"repeat": True})
    assert c2 in (200, 204, 401)
    if c2 == 204:
        assert ("_raw" not in b2) or (b2.get("_raw") == ""), f"204 须真空体：{b2}"
    elif c2 == 200:
        assert b2.get("requestId") and b2.get("data") is not None and "error" not in b2, b2
    else:
        assert b2.get("requestId") and (b2.get("error") or {}).get("code"), b2
    row2 = CC.scalar("SELECT status||'|'||destination_revision::text||'|'||"
                     f"coalesce(invalidated_at::text,'') FROM notification_destinations "
                     f"WHERE installation_id='{inst}'")
    parts = row.split("|")
    assert parts[0] == "invalid" and int(parts[1]) == int(rev0) + 1 and parts[2]
    assert row2 == row, (row, row2)
    _device_done(se, 3)


@_mark("SC-01-18", "P1", "联调", ["B"], ["D02"])
def test_SC_01_18(scenario_evidence):
    """后端可先验：**常驻周期自动**触发但无有效目标 → 不伪报 submitted/delivered。"""
    se = scenario_evidence
    se.doubles.add("push_channel", "double", "推送通道 dev 替身")
    se.doubles.add("gimbal_device", "double", "设备 dev 替身")
    sess = live.app_login("sc0118")
    g, _rev = _status(sess)
    CC.sql(f"UPDATE gimbals SET last_seen_at = now() - interval '1 hour',"
           f" connection_status='online' WHERE id='{g}'")
    env = {"MVP_NOTIFY_OFFLINE_THRESHOLD_SECONDS": "1",
           "MVP_WORKER_INCIDENT_SCAN_INTERVAL_SECONDS": "2",
           "MVP_WORKER_MEDIA_CLEANUP_SCAN_INTERVAL_SECONDS": "2",
           "MVP_WORKER_POLL_INTERVAL_SECONDS": "1"}
    live.start_resident_worker(env)
    try:
        time.sleep(8)
        delivered = CC.scalar("SELECT count(*) FROM notifications "
                              f"WHERE gimbal_id='{g}' AND status IN ('submitted','delivered')")
        se.record_raw(method="OBSERVE", path="resident-worker 无有效目标", status=0,
                      request_headers={}, request_json={"env": env},
                      response_excerpt=f"submitted_or_delivered={delivered}", started_at=0.0, elapsed_ms=0.0)
        assert delivered == "0", delivered
    finally:
        live.stop_resident_worker()
    _device_done(se, 2)
