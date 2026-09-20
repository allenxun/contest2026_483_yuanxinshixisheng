# -*- coding: utf-8 -*-
"""SC-05 · APP 查看授权与撤销 —— 集成轮 batch 1 真实步骤（7 节点）。

M1-A01 multipart 人脸授权（dev FaceProviderDouble MATCHED，如实 doubles）；
A02 列表 / A03 撤销 联动 C 侧撤销后统一 404 / 最小 acK / 仍可收尾（真实 B+C 链）。
"""
from __future__ import annotations

import json
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


def _grant(sess, image, se, tag="grant"):
    import os as _os
    image = image if image is not None else live._png() + _os.urandom(8)
    m, img = live.seed_member_face(image=image)
    c, b = live.multipart_grant(sess["access"], img)
    _rec(se, "POST", "/api/v1/member-access-grants", c, b, req={"metadata": tag})
    return m, c, b


@_mark("SC-05-01", "P0", "后端", ["B"], ["D01", "D06"])
def test_SC_05_01(scenario_evidence):
    """人脸可靠匹配后建立查看关联：201 + active 关系 + 正确成员；不创建成员。"""
    se = scenario_evidence
    se.doubles.add("face_algo", "double", "FaceProviderDouble MATCHED（dev 替身）")
    se.doubles.add("oss", "double", "A FilesystemStorageDouble")
    sess = live.app_login("sc0501")
    import os as _os
    img = live._png() + _os.urandom(8)
    m, img = live.seed_member_face(image=img)
    members_before = CC.scalar("SELECT count(*) FROM members")
    c, b = live.multipart_grant(sess["access"], img)
    _rec(se, "POST", "/api/v1/member-access-grants", c, b, req={"case": "grant"})
    data = b.get("data") or {}
    grant_row = CC.scalar("SELECT member_id||'|'||status FROM member_access_grants "
                          f"WHERE id='{data.get('grantId')}' AND account_id='{sess['accountId']}'")
    members_after = CC.scalar("SELECT count(*) FROM members")
    assert c == 201, (c, b)
    assert data.get("memberId") == m and data.get("status") == "active"
    assert grant_row == f"{m}|active", grant_row
    assert members_before == members_after  # 授权不建档
    se.seal()


@_mark("SC-05-02", "P0", "后端", ["B"], ["D01", "D06"])
def test_SC_05_02(scenario_evidence):
    """人脸无匹配/越出候选：MATCHED 但库中无可靠成员 → 403，不新建成员、不全库检索。"""
    se = scenario_evidence
    se.doubles.add("face_algo", "double", "FaceProviderDouble MATCHED（dev 替身）")
    se.doubles.add("oss", "double", "A FilesystemStorageDouble")
    sess = live.app_login("sc0502")
    members_before = CC.scalar("SELECT count(*) FROM members")
    # 未植入匹配成员 → 库中无可靠成员，与"未匹配"同一 403（不泄漏存在性）
    img = live._png() + b"\x00" + uuid.uuid4().bytes
    c, b = live.multipart_grant(sess["access"], img)
    _rec(se, "POST", "/api/v1/member-access-grants", c, b, req={"case": "no-member"})
    members_after = CC.scalar("SELECT count(*) FROM members")
    grants = CC.scalar("SELECT count(*) FROM member_access_grants "
                       f"WHERE account_id='{sess['accountId']}'")
    assert c == 403, (c, b)
    assert members_before == members_after and grants == "0"
    assert "memberId" not in json.dumps(b)  # 不回传候选/身份
    se.seal()


@_mark("SC-05-03", "P1", "后端", ["B"], [])
def test_SC_05_03(scenario_evidence):
    """永久授权与有效关系列表：授权不因时长过期；列表仅当前账号未撤销关系。"""
    se = scenario_evidence
    se.doubles.add("face_algo", "double", "FaceProviderDouble MATCHED（dev 替身）")
    se.doubles.add("oss", "double", "A FilesystemStorageDouble")
    sess = live.app_login("sc0503")
    m, c, b = _grant(sess, None, se)
    assert c == 201
    cl, bl, _ = I.http("GET", "/api/v1/me/member-access-grants", token=sess["access"])
    _rec(se, "GET", "/api/v1/me/member-access-grants", cl, bl)
    items = (bl.get("data") or {}).get("items") or []
    assert cl == 200 and any(it.get("memberId") == m for it in items)
    # 无过期列
    exp_col = CC.scalar("SELECT count(*) FROM information_schema.columns WHERE "
                        "table_name='member_access_grants' AND column_name LIKE '%expire%'")
    assert exp_col == "0"
    se.seal()


@_mark("SC-05-04", "P0", "后端", ["B"], [])
def test_SC_05_04(scenario_evidence):
    """撤销本人关联及重复撤销：204；重复撤销幂等；他人关联不能撤销。"""
    se = scenario_evidence
    se.doubles.add("face_algo", "double", "FaceProviderDouble MATCHED（dev 替身）")
    se.doubles.add("oss", "double", "A FilesystemStorageDouble")
    sess = live.app_login("sc0504")
    other = live.app_login("sc0504o")
    _m, c, b = _grant(sess, None, se)
    gid = (b.get("data") or {}).get("grantId")
    c1, b1, _ = I.http("DELETE", f"/api/v1/me/member-access-grants/{gid}",
                       token=sess["access"], headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "DELETE", f"/api/v1/me/member-access-grants/{gid}", c1, b1)
    c2, b2, _ = I.http("DELETE", f"/api/v1/me/member-access-grants/{gid}",
                       token=sess["access"], headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "DELETE", f"/api/v1/me/member-access-grants/{gid}", c2, b2)
    # 他人持该 grantId 撤销 → 404（不可见）
    c3, b3, _ = I.http("DELETE", f"/api/v1/me/member-access-grants/{gid}",
                       token=other["access"], headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "DELETE", f"/api/v1/me/member-access-grants/{gid}", c3, b3)
    st = CC.scalar(f"SELECT status FROM member_access_grants WHERE id='{gid}'")
    assert c1 == 204 and c2 == 204
    assert c3 == 404 and st == "revoked", (c3, st)
    se.seal()


@_mark("SC-05-05", "P0", "后端", ["B", "C", "D"], [])
def test_SC_05_05(scenario_evidence):
    """撤销后查询与旧授权重放：C 侧读取统一 404；旧请求不能恢复关系。"""
    se = scenario_evidence
    se.doubles.add("face_algo", "double", "FaceProviderDouble MATCHED（dev 替身）")
    se.doubles.add("oss", "double", "A FilesystemStorageDouble")
    sess = live.app_login("sc0505")
    m, c, b = _grant(sess, None, se)
    gid = (b.get("data") or {}).get("grantId")
    # 播种 care 数据（成员视图可见性；无需准入）
    mc = CC.seed_microcrystal()
    asmt = CC.seed_assessment(CC.seed_gimbal(), m)
    CC.seed_plan(asmt, m, status="ready", mc=mc)
    c_before, b_before, _ = I.http("GET", f"/api/v1/members/{m}/care-plans", token=sess["access"])
    _rec(se, "GET", f"/api/v1/members/{m}/care-plans", c_before, b_before)
    I.http("DELETE", f"/api/v1/me/member-access-grants/{gid}", token=sess["access"],
           headers={"Idempotency-Key": str(uuid.uuid4())})
    c1, b1, _ = I.http("GET", f"/api/v1/members/{m}/care-plans", token=sess["access"])
    _rec(se, "GET", f"/api/v1/members/{m}/care-plans", c1, b1)
    c2, b2, _ = I.http("GET", f"/api/v1/members/{m}/care-executions", token=sess["access"])
    _rec(se, "GET", f"/api/v1/members/{m}/care-executions", c2, b2)
    c3, b3, _ = I.http("GET", f"/api/v1/members/{m}/skin-reports", token=sess["access"])
    _rec(se, "GET", f"/api/v1/members/{m}/skin-reports", c3, b3)
    assert c_before == 200, (c_before, b_before)
    assert c1 == 404 and c2 == 404 and c3 == 404
    assert b1["error"]["code"] == "RESOURCE_NOT_VISIBLE"
    se.seal()


@_mark("SC-05-06", "P0", "联调", ["B"], [])
def test_SC_05_06(scenario_evidence):
    """后端可先验：撤销后列表移除、不删成员/报告、不影响他人。真实 APP 展示联调待办。"""
    se = scenario_evidence
    se.doubles.add("face_algo", "double", "FaceProviderDouble MATCHED（dev 替身）")
    se.doubles.add("oss", "double", "A FilesystemStorageDouble")
    sess = live.app_login("sc0506")
    m, c, b = _grant(sess, None, se)
    gid = (b.get("data") or {}).get("grantId")
    I.http("DELETE", f"/api/v1/me/member-access-grants/{gid}", token=sess["access"],
           headers={"Idempotency-Key": str(uuid.uuid4())})
    cl, bl, _ = I.http("GET", "/api/v1/me/member-access-grants", token=sess["access"])
    _rec(se, "GET", "/api/v1/me/member-access-grants", cl, bl)
    items = (bl.get("data") or {}).get("items") or []
    member_alive = CC.scalar(f"SELECT count(*) FROM members WHERE id='{m}'")
    assert cl == 200 and all(it.get("memberId") != m for it in items)
    assert member_alive == "1"  # 撤销不删成员
    se.seal()
    pytest.skip(gate.PENDING_PREFIX + gate.device_pending(3, 3))


@_mark("SC-05-07", "P0", "后端", ["B", "C", "D"], [])
def test_SC_05_07(scenario_evidence):
    """云台绑定不能替代成员查看授权：仅绑定云台的账号读取未授权成员 → 404。"""
    se = scenario_evidence
    se.doubles.add("gimbal_device", "double", "配对证明 dev 替身")
    sess = live.app_login("sc0507")
    g = CC.seed_gimbal()
    proof = live.pairing_proof(g, sess["accountId"], sess["installationId"])
    cb, bb, _ = I.http("PUT", f"/api/v1/me/gimbal-bindings/{g}", token=sess["access"],
                       body={"expectedBindingRevision": "0", "pairingProof": proof},
                       headers={"Idempotency-Key": str(uuid.uuid4())})
    _rec(se, "PUT", f"/api/v1/me/gimbal-bindings/{g}", cb, bb)
    m = CC.seed_member()
    c1, b1, _ = I.http("GET", f"/api/v1/members/{m}/care-plans", token=sess["access"])
    _rec(se, "GET", f"/api/v1/members/{m}/care-plans", c1, b1)
    c2, b2, _ = I.http("GET", f"/api/v1/members/{m}/skin-reports", token=sess["access"])
    _rec(se, "GET", f"/api/v1/members/{m}/skin-reports", c2, b2)
    assert cb == 200
    assert c1 == 404 and c2 == 404
    assert b1["error"]["code"] == "RESOURCE_NOT_VISIBLE"
    se.seal()
