# -*- coding: utf-8 -*-
"""框架自检（真实执行）：门控、客户端、隔离、替身登记、marker 注册。

这些测试与 A 基线无关，任何时候都必须真实通过（selfcheck 退出码 0 的依据）。
"""
from __future__ import annotations

import json
import pathlib

import pytest

from framework import client, doubles, gate, isolation

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ---------- baseline 门控 ----------

def test_baseline_file_shape():
    data = gate.load_baseline()
    assert data["gate"] in gate.VALID_GATES
    assert "sha" in data["a_baseline"] and "synced_at" in data["a_baseline"]


def test_baseline_gate_closed_implies_no_sha(tmp_path):
    bad = tmp_path / "b1.json"
    bad.write_text(json.dumps({"a_baseline": {"sha": None, "synced_at": None},
                               "gate": "open"}), encoding="utf-8")
    with pytest.raises(ValueError):  # open 但无 SHA：fail-closed 拒绝
        gate.load_baseline(bad)
    ok = tmp_path / "b2.json"
    ok.write_text(json.dumps({"a_baseline": {"sha": "abc123", "synced_at": "2026-09-10T00:00:00Z"},
                              "gate": "open"}), encoding="utf-8")
    assert gate.current_gate(ok) == "open"


def test_gate_closed_skips_with_fixed_prefix(monkeypatch):
    monkeypatch.setattr(gate, "current_gate", lambda path=None: "closed")
    with pytest.raises(pytest.skip.Exception) as ei:
        gate.run_scenario_gate("SC-00-01")
    assert str(ei.value).startswith(gate.PENDING_PREFIX), "skip reason 必须以 dependency_pending: 开头"


def test_gate_open_without_steps_fails(monkeypatch):
    monkeypatch.setattr(gate, "current_gate", lambda path=None: "open")
    with pytest.raises(pytest.fail.Exception) as ei:
        gate.run_scenario_gate("SC-00-01")
    assert "scenario steps not yet authored" in str(ei.value)


def test_scenarios_matrix_loadable_for_all_94():
    m = gate.load_scenarios()
    assert len(m) == 94 and all(v["pending_reason"] for v in m.values())


# ---------- 黑盒 HTTP 客户端 ----------

def test_client_rejects_non_http_base():
    with pytest.raises(ValueError):
        client.BlackBoxClient("jdbc:postgresql://localhost/db")


def test_client_constructs_and_evidence_records(tmp_path):
    c = client.BlackBoxClient("http://127.0.0.1:1", run_id="E-selfcheck-00000000",
                              evidence_dir=tmp_path)
    assert client.HEADER_REQUEST_ID == "X-Request-Id"
    assert c.recorder is not None  # 传入 evidence_dir 后必有记录器
    p = c.request.__name__
    rec_dir = tmp_path / "E-selfcheck-00000000"
    # 不发真实请求（无被测系统），只验证证据记录器机制：
    path = c.recorder.record({"method": "GET", "path": "/healthz", "status": 200,
                              "request_id": "r-1", "request_headers": {},
                              "request_json": None, "response_excerpt": "{}",
                              "started_at": 0.0, "elapsed_ms": 0.0, "run_id": "E-selfcheck-00000000"})
    assert path.exists() and path.read_text(encoding="utf-8").find("/healthz") > 0
    assert rec_dir.is_dir() and p == "request"


# ---------- 隔离机制 ----------

def test_run_id_unique_and_prefixed():
    a, b = isolation.new_run_id("E-a"), isolation.new_run_id("E-a")
    assert a != b and isolation.RUN_ID_RE.match(a)


def test_data_prefix_requires_valid_run_id():
    with pytest.raises(ValueError):
        isolation.data_prefix("DROP TABLE")
    rid = isolation.new_run_id("E")
    assert isolation.data_prefix(rid).startswith("EACC_")


def test_validate_env_safety_fail_closed():
    isolation.validate_env_safety({isolation.ENV_PG_DB: "eaccept_mvp_e_1", isolation.ENV_PG_PORT: "15432"})
    with pytest.raises(RuntimeError):
        isolation.validate_env_safety({isolation.ENV_PG_DB: "postgres"})
    with pytest.raises(RuntimeError):
        isolation.validate_env_safety({isolation.ENV_PG_DB: "eaccept_x", isolation.ENV_PG_PORT: "5432"})


def test_cleanup_plan_returns_mechanism_only():
    plan = isolation.cleanup_plan(isolation.new_run_id("E"), {isolation.ENV_PG_DB: "eaccept_demo"})
    assert isinstance(plan, list) and plan[0].startswith("确认 PG 库")


# ---------- 替身登记 ----------

def test_doubles_evidence_tag_conservative():
    mf = doubles.DoublesManifest("SC-02-05").add("face_algo", "double")
    assert mf.evidence_tag() == "doubles_pass"
    mf.add("oss", "real")
    assert mf.evidence_tag() == "mixed"
    with pytest.raises(AssertionError):
        mf.assert_claimable("real_pass")
    strict = doubles.DoublesManifest("SC-C-05").add("oss", "real")
    assert strict.evidence_tag() == "real_pass"
    strict.assert_claimable("real_pass")
    with pytest.raises(ValueError):
        doubles.DoublesManifest("x").add("k8s", "real")  # 未登记依赖类型


# ---------- 插件与 markers ----------

def test_markers_registered(pytestconfig):
    registered = "\n".join(pytestconfig.getini("markers"))
    for name in ("sc_id", "priority", "scope", "package", "deps"):
        assert f"{name}(" in registered, f"marker {name} 未注册"


def test_scenario_nodes_have_full_markers():
    """加载各场景模块，验证 94 个节点一一对应、命名含场景 ID、markers 齐全。"""
    import importlib.util
    m = gate.load_scenarios()
    fname2sid = {"test_" + sid.replace("-", "_"): sid for sid in m}
    seen: set[str] = set()
    for py in sorted((ROOT / "tests" / "scenarios").glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(py.stem, py)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name, fn in vars(mod).items():
            if name.startswith("test_") and callable(fn) and name in fname2sid:
                sid = fname2sid[name]
                marks = {mk.name for mk in getattr(fn, "pytestmark", [])}
                assert {"sc_id", "priority", "scope", "package"} <= marks, f"{sid} markers 不全：{marks}"
                if m[sid]["deps"]:
                    assert "deps" in marks, f"{sid} 有 deps 却无 deps marker"
                seen.add(sid)
    assert seen == set(m), f"节点覆盖缺口：{sorted(set(m) - seen)}"
