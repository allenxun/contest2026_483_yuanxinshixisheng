# -*- coding: utf-8 -*-
"""V3 三组评分（pores/spots/surface_gloss）：发布携带 + 严格发布前校验。

覆盖（判别性）：
1. 校验器矩阵：all-or-none、闭合键白名单（组/区域）、score 0..100 或 null（bool 拒绝）、
   severity 冻结词表或 null、name/region 非空且逐字保留、区域唯一、结构类型；
2. 深拷贝隔离；
3. 发布集成：三组落在 T05 ``report_payload`` 顶层（恰好三键）、mock 标记、null 存 null；
   all-or-none/非法 → 既有终态 ``PROVIDER_CONTRACT_VIOLATION`` 且 payload 未发布；
   缺省 → payload 不含三键；
4. 开关：默认 OFF 不携带；ON（dev）携带；生产信号 + ON → fail-closed；非法布尔 fail fast。

数据来源：``.mvp-d-runtime/v3-probe-input/`` 的 mock（**非**算法证据）。
"""
from __future__ import annotations

import copy
import json
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from conftest import enqueue
from d_support import (
    DEFAULT_NS,
    clean_d_tables,
    fetch_assessment,
    photo_versions_for,
    run_claimed,
    seed_assessment,
    seed_member,
    seed_source_media,
)
from mvp_worker.handlers.assessment_analyze import (
    _ContractViolation,
    _validate_v3_skin_groups,
    handler as analyze_handler,
)
from mvp_worker.handlers.dshared.dconfig import (
    SKIN_V3_MOCK_ENV,
    DConfig,
    ProviderConfigError,
    assert_no_double_injection_in_production,
    double_injection_overrides,
)
from mvp_worker.handlers.dshared.dskin_mock import (
    V3_SKIN_GROUP_KEYS,
    V3_SKIN_MOCK_GROUPS,
    V3_SKIN_MOCK_MODEL_VERSION,
    V3_SKIN_SEVERITIES,
)
from mvp_worker.handlers.dshared.providers import FaceDouble, SkinDouble, build_skin_port
from mvp_worker.media.storage import FilesystemStorageDouble

_V3_ENVS = (SKIN_V3_MOCK_ENV,)
_PROD_SIGNALS = ("APP_ENV", "MVP_NOTIFY_ENV", "MVP_WORKER_ENVIRONMENT", "SPRING_PROFILES_ACTIVE")


@pytest.fixture(autouse=True)
def _clean_d(engine: Engine) -> Any:
    clean_d_tables(engine)
    yield
    clean_d_tables(engine)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: Any) -> None:
    for name in _V3_ENVS + _PROD_SIGNALS:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------- helpers


def _mock() -> dict[str, Any]:
    return copy.deepcopy(V3_SKIN_MOCK_GROUPS)


def _attach_photo_versions(
    engine: Engine, assessment_id: str, version: int, images: dict[str, str]
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE skin_assessments SET photo_versions = CAST(:pv AS jsonb)"
                " WHERE id = CAST(:id AS uuid)"
            ),
            {"pv": json.dumps(photo_versions_for(version, images)), "id": assessment_id},
        )


def _seed_analysis_case(
    engine: Engine, tmp_path: Any, *, ref: str, rev: int = 2
) -> tuple[FilesystemStorageDouble, str]:
    storage = FilesystemStorageDouble(tmp_path / "storage")
    aid = seed_assessment(
        engine, status="queued", current_photo_version=1, processing_revision=rev
    )
    images = seed_source_media(engine, storage, assessment_id=aid, photo_version=1)
    _attach_photo_versions(engine, aid, 1, images)
    seed_member(engine, ns=DEFAULT_NS, ref=ref, assessment_id=aid)
    return storage, aid


def _enqueue_analyze(engine: Engine, aid: str, rev: int) -> str:
    jid, _ = enqueue(
        engine,
        job_type="assessment.analyze",
        dedup_key=f"assessment:{aid}:{rev}",
        owner_type="assessment",
        owner_id=aid,
        input_revision=rev,
        payload={"schema_version": 1, "assessment_id": aid, "processing_revision": str(rev)},
        max_attempts=5,
    )
    return jid


def _run_publish(
    engine: Engine, tmp_path: Any, skin: SkinDouble
) -> tuple[str, Any, str, dict[str, Any]]:
    ref = str(uuid.uuid4())
    storage, aid = _seed_analysis_case(engine, tmp_path, ref=ref)
    jid = _enqueue_analyze(engine, aid, 2)
    face = FaceDouble(search="matched", face_subject_ref=ref)
    status, exc, _ = run_claimed(
        engine, analyze_handler, jid,
        extras={"storage": storage, "face_port": face, "skin_port": skin},
    )
    return status, exc, aid, fetch_assessment(engine, aid)


# ================================================================ 1) 校验器矩阵


def test_validator_accepts_mock_and_is_isolated() -> None:
    source = _mock()
    normalized = _validate_v3_skin_groups(source)
    assert normalized is not None
    assert set(normalized) == set(V3_SKIN_GROUP_KEYS)
    # 值逐字保留（含画面左右措辞与 null）
    assert normalized == source
    assert normalized is not source
    # 深拷贝隔离：改动来源不影响结果
    source["spots"]["regions"][0]["score"] = 999
    source["pores"]["name"] = "changed"
    assert normalized["spots"]["regions"][0]["score"] == 38.0
    assert normalized["pores"]["name"] == "毛孔"


def test_validator_absent_returns_none() -> None:
    assert _validate_v3_skin_groups(None) is None


@pytest.mark.parametrize(
    "payload",
    [
        {},  # 全缺
        {"pores": _mock()["pores"]},  # 只有一组
        {"pores": _mock()["pores"], "spots": _mock()["spots"]},  # 只有两组
        {**_mock(), "extra_group": {}},  # 未知顶层键
        {"pores": "nope", "spots": _mock()["spots"], "surface_gloss": _mock()["surface_gloss"]},
    ],
)
def test_validator_rejects_all_or_none_and_structure(payload: Any) -> None:
    with pytest.raises(_ContractViolation):
        _validate_v3_skin_groups(payload)


def _with_group(mutator: Any) -> dict[str, Any]:
    payload = _mock()
    mutator(payload["pores"])
    return payload


@pytest.mark.parametrize(
    "mutator",
    [
        lambda g: g.__setitem__("extra_key", 1),  # 组未知键
        lambda g: g.pop("score"),  # 缺必需键
        lambda g: g.pop("regions"),
        lambda g: g.__setitem__("score", 101.0),  # 越界
        lambda g: g.__setitem__("score", -1.0),
        lambda g: g.__setitem__("score", True),  # bool 拒绝
        lambda g: g.__setitem__("score", "50"),  # 字符串拒绝
        lambda g: g.__setitem__("severity", "很严重"),  # 词表外
        lambda g: g.__setitem__("name", ""),  # 空名
        lambda g: g.__setitem__("regions", "not-a-list"),
    ],
)
def test_validator_group_invalid_matrix(mutator: Any) -> None:
    payload = _with_group(mutator)
    with pytest.raises(_ContractViolation):
        _validate_v3_skin_groups(payload)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda r: r.__setitem__("extra_key", 1),  # 区域未知键
        lambda r: r.pop("region"),
        lambda r: r.pop("severity"),
        lambda r: r.__setitem__("region", ""),
        lambda r: r.__setitem__("name", ""),
        lambda r: r.__setitem__("score", 100.5),
        lambda r: r.__setitem__("score", False),
        lambda r: r.__setitem__("severity", "nope"),
    ],
)
def test_validator_region_item_matrix(mutator: Any) -> None:
    payload = _mock()
    mutator(payload["pores"]["regions"][0])
    with pytest.raises(_ContractViolation):
        _validate_v3_skin_groups(payload)


def test_validator_rejects_duplicate_region_and_bad_item() -> None:
    dup = _mock()
    dup["pores"]["regions"][1]["region"] = dup["pores"]["regions"][0]["region"]
    with pytest.raises(_ContractViolation):
        _validate_v3_skin_groups(dup)

    bad_item = _mock()
    bad_item["pores"]["regions"][0] = "not-an-object"
    with pytest.raises(_ContractViolation):
        _validate_v3_skin_groups(bad_item)


def test_validator_accepts_null_score_and_severity() -> None:
    payload = _mock()
    payload["pores"]["score"] = None
    payload["pores"]["severity"] = None
    payload["spots"]["regions"][0]["score"] = None
    payload["spots"]["regions"][0]["severity"] = None
    normalized = _validate_v3_skin_groups(payload)
    assert normalized is not None
    assert normalized["pores"]["score"] is None
    assert normalized["pores"]["severity"] is None
    assert normalized["spots"]["regions"][0]["score"] is None
    # 绝不把 null 变 0
    assert normalized["spots"]["regions"][0]["score"] != 0


def test_severity_vocabulary_matches_field_doc() -> None:
    assert V3_SKIN_SEVERITIES == ("未见明显", "轻度", "中度", "较明显", "显著")
    for group in V3_SKIN_MOCK_GROUPS.values():
        if group["severity"] is not None:
            assert group["severity"] in V3_SKIN_SEVERITIES
        for region in group["regions"]:
            if region["severity"] is not None:
                assert region["severity"] in V3_SKIN_SEVERITIES


# ================================================================ 2) 发布集成


def test_publish_includes_v3_groups_exact_whitelist(engine: Engine, tmp_path: Any) -> None:
    skin = SkinDouble(
        v3_groups=_mock(), model_version=V3_SKIN_MOCK_MODEL_VERSION
    )
    status, exc, _aid, assessment = _run_publish(engine, tmp_path, skin)
    assert status == "succeeded", (status, exc)
    payload = assessment["report_payload"]
    assert isinstance(payload, dict)
    # 恰好三键落在顶层（白名单深拷贝）
    for key in V3_SKIN_GROUP_KEYS:
        assert key in payload
    assert {"pores", "spots", "surface_gloss"} <= set(payload)
    assert payload["pores"] == V3_SKIN_MOCK_GROUPS["pores"]
    assert payload["spots"] == V3_SKIN_MOCK_GROUPS["spots"]
    assert payload["surface_gloss"] == V3_SKIN_MOCK_GROUPS["surface_gloss"]
    # mock 标记（model_info.model_version 含 "mock"）
    assert "mock" in payload["model_info"]["model_version"]
    # 画面左右 / region / name 逐字保留
    names = {
        region["name"]
        for key in V3_SKIN_GROUP_KEYS
        for region in payload[key]["regions"]
    }
    assert "画面左鼻旁" in names and "画面右面颊" in names


def test_publish_null_score_stored_as_null_not_zero(engine: Engine, tmp_path: Any) -> None:
    skin = SkinDouble(v3_groups=_mock(), model_version=V3_SKIN_MOCK_MODEL_VERSION)
    status, exc, _aid, assessment = _run_publish(engine, tmp_path, skin)
    assert status == "succeeded", (status, exc)
    spots = assessment["report_payload"]["spots"]["regions"]
    null_region = next(r for r in spots if r["region"] == "right_cheek")
    assert null_region["score"] is None
    assert null_region["severity"] is None
    assert null_region["score"] != 0
    # JSON 往返仍是 null（不是 0）
    assert '"score": null' in json.dumps(assessment["report_payload"]) or "None" in str(
        assessment["report_payload"]
    )


def test_publish_absent_v3_leaves_payload_without_groups(engine: Engine, tmp_path: Any) -> None:
    status, exc, _aid, assessment = _run_publish(engine, tmp_path, SkinDouble())
    assert status == "succeeded", (status, exc)
    payload = assessment["report_payload"]
    for key in V3_SKIN_GROUP_KEYS:
        assert key not in payload


@pytest.mark.parametrize(
    "bad_groups",
    [
        {"pores": copy.deepcopy(V3_SKIN_MOCK_GROUPS["pores"])},  # all-or-none
        {
            **{k: copy.deepcopy(V3_SKIN_MOCK_GROUPS[k]) for k in V3_SKIN_GROUP_KEYS},
            "extra": {},
        },
    ],
)
def test_publish_all_or_none_violation_is_terminal(
    engine: Engine, tmp_path: Any, bad_groups: Any
) -> None:
    skin = SkinDouble(v3_groups=bad_groups, model_version=V3_SKIN_MOCK_MODEL_VERSION)
    status, exc, _aid, assessment = _run_publish(engine, tmp_path, skin)
    assert status == "failed"
    assert exc is not None and exc.code == "PROVIDER_CONTRACT_VIOLATION"
    assert exc.retryable is False
    assert assessment["report_payload"] is None
    assert assessment["report_id"] is None
    assert assessment["failure_code"] == "PROVIDER_CONTRACT_VIOLATION"


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda g: g["pores"].__setitem__("unknown_key", 1),  # 组未知键
        lambda g: g["pores"].__setitem__("score", 101.0),  # 越界
        lambda g: g["pores"]["regions"][1].__setitem__(
            "region", g["pores"]["regions"][0]["region"]
        ),  # 区域重复
        lambda g: g["spots"]["regions"][0].__setitem__("severity", "不存在"),  # 词表外
    ],
)
def test_publish_invalid_v3_is_terminal_and_unpolluted(
    engine: Engine, tmp_path: Any, corrupt: Any
) -> None:
    groups = _mock()
    corrupt(groups)
    skin = SkinDouble(v3_groups=groups, model_version=V3_SKIN_MOCK_MODEL_VERSION)
    status, exc, _aid, assessment = _run_publish(engine, tmp_path, skin)
    assert status == "failed"
    assert exc is not None and exc.code == "PROVIDER_CONTRACT_VIOLATION"
    assert assessment["report_payload"] is None


def test_double_analyze_returns_independent_copies() -> None:
    double = SkinDouble(v3_groups=_mock())
    first = double.analyze({})
    second = double.analyze({})
    assert first.v3_groups == second.v3_groups
    assert first.v3_groups is not second.v3_groups
    first.v3_groups["pores"]["name"] = "mutated"
    assert second.v3_groups["pores"]["name"] == "毛孔"
    # 也不回写构造来源
    assert V3_SKIN_MOCK_GROUPS["pores"]["name"] == "毛孔"


# ================================================================ 3) 开关 / 生产守卫


def test_v3_mock_default_off_serves_no_v3(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_SKIN_PROVIDER", "double")
    port = build_skin_port(DConfig.from_env(), environment="dev")
    assert port.analyze({}).v3_groups is None


def test_v3_mock_on_serves_marked_v3(monkeypatch: Any) -> None:
    monkeypatch.setenv("MVP_D_SKIN_PROVIDER", "double")
    monkeypatch.setenv(SKIN_V3_MOCK_ENV, "true")
    port = build_skin_port(DConfig.from_env(), environment="dev")
    result = port.analyze({})
    assert result.v3_groups is not None
    assert set(result.v3_groups) == set(V3_SKIN_GROUP_KEYS)
    assert "mock" in result.model_version


def test_v3_mock_production_signal_refused(monkeypatch: Any) -> None:
    monkeypatch.setenv(SKIN_V3_MOCK_ENV, "true")
    monkeypatch.setenv("APP_ENV", "production")
    assert SKIN_V3_MOCK_ENV in double_injection_overrides()
    with pytest.raises(ProviderConfigError):
        assert_no_double_injection_in_production()


def test_v3_mock_strict_bool_invalid_fails_fast(monkeypatch: Any) -> None:
    monkeypatch.setenv(SKIN_V3_MOCK_ENV, "maybe")
    with pytest.raises(ProviderConfigError) as ei:
        DConfig.from_env()
    assert SKIN_V3_MOCK_ENV in str(ei.value)


def test_v3_mock_off_with_production_signals_passes(monkeypatch: Any) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    assert double_injection_overrides() == {}
    assert_no_double_injection_in_production()  # 默认关闭不触发
