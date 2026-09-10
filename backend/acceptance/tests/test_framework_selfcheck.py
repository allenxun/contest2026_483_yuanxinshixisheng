# -*- coding: utf-8 -*-
"""框架自检（真实执行）：门控、客户端、隔离、替身登记、marker 注册。

这些测试与 A 基线无关，任何时候都必须真实通过（selfcheck 退出码 0 的依据）。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess

import pytest

from framework import client, doubles, gate, isolation

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run(cmd: list[str], env_extra: dict[str, str], timeout: int = 300) -> subprocess.CompletedProcess:
    # 先清空继承的 PYTEST_ADDOPTS，守卫子进程的选项集只能由用例显式指定。
    env = {**os.environ, "PYTEST_ADDOPTS": "", **env_extra}
    return subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True,
                          text=True, timeout=timeout)


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


# ---------- 发现A：matrix 假 0 双层守卫（插件结算守卫 + run.sh 入口拒绝/哨兵） ----------

NESTED = {"E_SELFCHECK_NESTED": "1"}  # 嵌套运行中守卫用例直接返回，防递归


def _direct_pytest(addopts: str) -> subprocess.CompletedProcess:
    """绕过 run.sh 直调 pytest，验证插件层结算守卫本身不依赖入口。"""
    return _run(["./.venv/bin/pytest", "tests/", "-q"],
                {**NESTED, "E_ACCEPTANCE_MODE": "matrix", "PYTEST_ADDOPTS": addopts})


def test_plugin_guard_zero_scenario_collection_fails():
    """直接 pytest --ignore 掉 94 场景：插件守卫必须 4，绝不 0。"""
    if os.environ.get("E_SELFCHECK_NESTED"):
        return
    r = _direct_pytest("-p no:cacheprovider --ignore=tests/scenarios")
    out = r.stdout + r.stderr
    assert r.returncode == 4, f"期望 4，实际 {r.returncode}：\n{out[-1500:]}"
    assert "SETTLEMENT_INCOMPLETE" in out and "DEPENDENCY_PENDING=0" in out, out[-800:]


def test_plugin_guard_deselect_scenarios_fails():
    """-m 'not sc_id' 反选全部场景：deselect 计入守卫 → 4。"""
    if os.environ.get("E_SELFCHECK_NESTED"):
        return
    r = _direct_pytest("-m 'not sc_id'")
    out = r.stdout + r.stderr
    assert r.returncode == 4, f"期望 4，实际 {r.returncode}：\n{out[-1500:]}"
    assert "SETTLEMENT_INCOMPLETE" in out, out[-800:]


def test_runsh_refuses_pytest_addopts_plugin_disable():
    """oracle 精确绕过命令：run.sh 必须在进入 pytest 前拒绝并 exit 4。"""
    if os.environ.get("E_SELFCHECK_NESTED"):
        return
    r = _run(["./run.sh", "matrix"],
             {**NESTED, "PYTEST_ADDOPTS": "-p no:framework.conftest -o addopts= "
              "--ignore=tests/test_framework_selfcheck.py "
              "--ignore=tests/test_matrix_integrity.py"})
    out = r.stdout + r.stderr
    assert r.returncode == 4, f"期望 4，实际 {r.returncode}：\n{out[-800:]}"
    assert "PYTEST_ADDOPTS" in out and "exit 4" in out, out[-800:]


def test_runsh_refuses_pytest_addopts_ignore_variant():
    """第一轮 oracle 复现命令同样在入口被拒绝 → 4。"""
    if os.environ.get("E_SELFCHECK_NESTED"):
        return
    r = _run(["./run.sh", "matrix"],
             {**NESTED, "PYTEST_ADDOPTS": "-p no:cacheprovider --ignore=tests/scenarios"})
    assert r.returncode == 4, (r.stdout + r.stderr)[-800:]


def test_full_matrix_settles_exactly_94_and_writes_sentinel():
    """正常入口：rc=3、SETTLED=94/94，且哨兵文件存在并与汇总一致。"""
    if os.environ.get("E_SELFCHECK_NESTED"):
        return
    r = _run(["./run.sh", "matrix"], NESTED)
    out = r.stdout + r.stderr
    assert "SETTLED=94/94" in out and "SETTLEMENT_OK" in out, out[-800:]
    assert "DEPENDENCY_PENDING=94" in out, out[-800:]
    assert r.returncode == 3, f"gate=closed 时完整矩阵应为 3，实际 {r.returncode}"
    m = re.search(r"RUN_ID=(\S+)", out)
    assert m, "汇总行缺 RUN_ID"
    sent = ROOT / "reports" / m.group(1) / "settlement.json"
    assert sent.exists(), f"哨兵缺失：{sent}"
    d = json.loads(sent.read_text(encoding="utf-8"))
    assert d["run_id"] == m.group(1) and d["mode"] == "matrix"
    assert d["completed"] is True and d["settlement_ok"] is True
    assert d["settled_unique"] == 94 and d["counts"]["pending"] == 94


# ---------- 发现2：证据默认无条件脱敏凭据头 ----------

def test_evidence_redacts_credentials_by_default(tmp_path):
    class FakeResp:
        status_code = 200
        text = '{"ok":true}'
        headers = {}

    class FakeSession:
        def request(self, method, url, **kw):
            return FakeResp()

    c = client.BlackBoxClient("http://example.invalid", run_id="E-redact-00000000",
                              evidence_dir=tmp_path)
    c._session = FakeSession()  # type: ignore[assignment]  # 无网络：只验证证据序列化路径
    c.get("/api/v1/me/gimbal-bindings/G1", auth_header="Bearer SUPER-SECRET-TOKEN",
          headers={"Cookie": "sess=abc", "X-Api-Key": "key-123",
                   "Proxy-Authorization": "Basic zzz", "My-Extra": "hide-me"})
    files = list((tmp_path / "E-redact-00000000").glob("*.json"))
    assert len(files) == 1
    blob = files[0].read_text(encoding="utf-8")
    for secret in ("SUPER-SECRET-TOKEN", "sess=abc", "key-123", "Basic zzz"):
        assert secret not in blob, f"证据泄露凭据：{secret}"
    assert client.REDACTED in blob
    # 调用方只能追加、不能移除默认脱敏：
    again = client.safe_headers({"Authorization": "Bearer t2", "My-Extra": "v"},
                                ())  # 故意不声明额外项
    assert again["Authorization"] == client.REDACTED


def test_record_raw_cannot_bypass_redaction(tmp_path):
    """发现B回归：record_raw 直传含凭据的 request_headers 也必须被共同边界脱敏。"""
    from framework import conftest as e_plugin
    rec = client.EvidenceRecorder(tmp_path, "E-rawcheck-00000000")
    sm = e_plugin.ScenarioSettlement("SC-02-01", rec)
    sm.record_raw(method="GET", path="/x", status=200, request_id="r",
                  request_headers={"Authorization": "Bearer SUPER-SECRET",
                                   "Cookie": "session=SUPER-SECRET"},
                  request_json=None, response_excerpt="{}", started_at=0.0, elapsed_ms=0.0)
    blob = next((tmp_path / "E-rawcheck-00000000").glob("*.json")).read_text(encoding="utf-8")
    assert "SUPER-SECRET" not in blob, "record_raw 绕过了脱敏边界"
    assert client.REDACTED in blob


def test_record_run_id_is_real_run_id_not_scenario_dir(tmp_path):
    """MINOR 回归：证据 JSON 的 run_id 必须是真实 RUN_ID，而不是场景 ID 目录名。"""
    run_id, sc_id = "E-20260910T120000Z-abcdef01", "SC-02-01"
    rec = client.EvidenceRecorder(tmp_path, run_id, namespace=sc_id)
    assert rec.run_id == run_id and rec.dir == tmp_path / run_id / sc_id

    from framework import conftest as e_plugin
    sm = e_plugin.ScenarioSettlement(sc_id, rec)
    sm.record_raw(method="GET", path="/raw", status=200, request_id="r1",
                  request_headers={}, request_json=None, response_excerpt="{}",
                  started_at=0.0, elapsed_ms=0.0)
    # record() 路径（BlackBoxClient 风格）同样写入真实 RUN_ID
    rec.record({"method": "GET", "path": "/direct", "status": 200, "request_id": "r2",
                "request_headers": {}, "request_json": None, "response_excerpt": "{}",
                "started_at": 0.0, "elapsed_ms": 0.0, "run_id": run_id})

    files = sorted((tmp_path / run_id / sc_id).glob("*.json"))
    assert len(files) == 2
    for f in files:
        assert json.loads(f.read_text(encoding="utf-8"))["run_id"] == run_id, f.name


# ---------- 发现3：sc_id 节点 passed 必须绑定证据与替身声明 ----------

def _spawn_mini_suite(body: str, name: str) -> tuple[int, str]:
    """在 acceptance 树内（reports/_selfcheck/，git 忽略）生成最小场景文件并运行。

    rootdir/插件由向上搜索的 pytest.ini + 顶层 conftest 保证；模式用 selfcheck
    （结算守卫不启用），单独验证"passed 绑定证据"机制本身。
    """
    work = ROOT / "reports" / "_selfcheck" / name
    work.mkdir(parents=True, exist_ok=True)
    (work / "test_mini.py").write_text(body, encoding="utf-8")
    r = subprocess.run(["../../../.venv/bin/pytest", "test_mini.py", "-q"],
                       cwd=work, env={**os.environ, "PYTEST_ADDOPTS": "",
                                       "E_ACCEPTANCE_MODE": "selfcheck",
                                       "E_SELFCHECK_NESTED": "1"},
                       capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def test_bare_pass_without_evidence_is_flipped_to_fail():
    if os.environ.get("E_SELFCHECK_NESTED"):
        return
    body = (
        "import pytest\n\n"
        '@pytest.mark.sc_id("SC-00-01")\n'
        "def test_fake_bare_pass():\n"
        "    assert True\n"
    )
    rc, out = _spawn_mini_suite(body, "bare")
    assert rc == 1, f"带 sc_id 的裸通过必须被插件改判 fail：\n{out[-1200:]}"
    assert "pass without evidence" in out, out[-1200:]


def test_pass_with_sealed_evidence_and_doubles_is_allowed():
    if os.environ.get("E_SELFCHECK_NESTED"):
        return
    body = (
        "import pytest\n\n"
        '@pytest.mark.sc_id("SC-00-02")\n'
        "def test_fake_with_evidence(scenario_evidence):\n"
        "    se = scenario_evidence\n"
        "    se.doubles.add('oss', 'real')\n"
        "    se.seal()\n"
        "    se.record_raw(method='GET', path='/healthz', status=200, request_id='r1',\n"
        "                  request_headers={}, request_json=None, response_excerpt='{}',\n"
        "                  started_at=0.0, elapsed_ms=0.0)\n"
        "    assert True\n"
    )
    rc, out = _spawn_mini_suite(body, "sealed")
    assert rc == 0, f"已提交证据并封存替身声明的通过应正常判定：\n{out[-1200:]}"
    assert "1 passed" in out
