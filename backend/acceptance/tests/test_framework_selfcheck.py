# -*- coding: utf-8 -*-
"""框架自检（真实执行）：门控、客户端、隔离、替身登记、marker 注册。

这些测试与 A 基线无关，任何时候都必须真实通过（selfcheck 退出码 0 的依据）。
"""
from __future__ import annotations

import fcntl
import hashlib
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
    assert gate.load_baseline(ok)["gate"] == "open"


def test_gate_closed_skips_with_fixed_prefix(monkeypatch):
    monkeypatch.setattr(gate, "current_gate", lambda path=None: "closed")
    with pytest.raises(pytest.skip.Exception) as ei:
        gate.run_scenario_gate("SC-00-01")
    assert str(ei.value).startswith(gate.PENDING_PREFIX), "skip reason 必须以 dependency_pending: 开头"


def test_gate_open_without_steps_fails(monkeypatch):
    # SC-01-03 已在 batch1 编写步骤（staged_pending=false）→ 未经门控直跑视为未编写 → fail
    monkeypatch.setattr(gate, "current_gate", lambda path=None: "open")
    with pytest.raises(pytest.fail.Exception) as ei:
        gate.run_scenario_gate("SC-01-03")
    assert "scenario steps not yet authored" in str(ei.value)


def test_gate_open_staged_scenario_skips_pending(monkeypatch):
    # SC-R-01 显式 staged_pending=true → skip 且 reason=场景步骤编写中（集成轮 batch N）
    monkeypatch.setattr(gate, "current_gate", lambda path=None: "open")
    with pytest.raises(pytest.skip.Exception) as ei:
        gate.run_scenario_gate("SC-R-01")
    assert str(ei.value).startswith(gate.PENDING_PREFIX)
    assert "场景步骤编写中（集成轮" in str(ei.value)


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

NESTED = {"E_SELFCHECK_NESTED": "1", "E_ACCEPTANCE_FORCE_GATE": "closed"}
#: 嵌套守卫运行强制 gate=closed：验证结算机制本身，不触发 gate=open 的活体服务。


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


# ---------- 第五轮：a-baseline 结算门禁 + 诊断模式不落 evidence ----------

def _settle(pass_n=0, fail_n=0, blocked_n=0, info_n=0, expected=52, rows=None,
            missing=(), extra=(), duplicates=(), unknown=()):
    counts = {"pass": pass_n, "fail": fail_n, "blocked": blocked_n, "info": info_n}
    return {"expected": expected, "settled": rows if rows is not None else sum(counts.values()),
            "rows": rows if rows is not None else sum(counts.values()),
            "missing": list(missing), "extra": list(extra), "duplicates": list(duplicates),
            "unknown_status": list(unknown), "counts": counts,
            "pass": pass_n, "fail": fail_n, "blocked": blocked_n, "info": info_n}


def test_ab_conclusion_policy_unit_five_scenarios():
    """结论政策单元测试（跨 final_exit→conclusion_line，非真实运行）。"""
    from driver import a_baseline as ab
    # (a) 51 PASS + 1 BLOCKED 结算完整 → exit≠0 且结论无“通过（无附条件）”
    sa = _settle(pass_n=51, blocked_n=1)
    assert ab.final_exit(True, sa) == 1
    assert "未通过" in ab.conclusion_line(sa)
    # (b) 缺项 → exit 4 且结论为“未通过”（不得出现“结论：通过”）
    sb = _settle(pass_n=51, missing=["AB-03"])
    assert ab.final_exit(True, sb) == 4
    cb = ab.conclusion_line(sb)
    assert "未通过" in cb and "结论：通过" not in cb
    # (c) 51 PASS + 1 INFO 结算完整 → exit 0 且结论含附条件披露
    sc = _settle(pass_n=51, info_n=1)
    assert ab.final_exit(True, sc) == 0
    concl = ab.conclusion_line(sc)
    assert "通过（附条件）" in concl and "INFO" in concl
    # (d) 任一 FAIL → exit 1 未通过
    sd = _settle(pass_n=51, fail_n=1)
    assert ab.final_exit(True, sd) == 1 and "未通过" in ab.conclusion_line(sd)
    # (e) 未知状态 → 拒绝（exit 4）
    se = _settle(pass_n=51, blocked_n=0, unknown=["WEIRD"])
    assert ab.final_exit(True, se) == 4 and "拒绝" in ab.conclusion_line(se)


def test_ab_final_exit_settlement_gate():
    from driver import a_baseline as ab
    ok = _settle(pass_n=52)
    assert ab.final_exit(True, ok) == 0
    assert ab.final_exit(True, _settle(pass_n=51, missing=["AB-03"])) == 4
    assert ab.final_exit(True, _settle(pass_n=51, extra=["AB-XX"])) == 4
    assert ab.final_exit(True, _settle(pass_n=51, duplicates=["AB-03"])) == 4
    assert ab.final_exit(True, _settle(pass_n=51, fail_n=1)) == 1
    assert ab.final_exit(True, _settle(pass_n=51, blocked_n=1)) == 1     # BLOCKED 不算通过
    assert ab.final_exit(False, _settle(pass_n=51, missing=["AB-03"])) == 0  # 诊断不判 4


def test_ab_settlement_counts_sum_and_info():
    from driver import a_baseline as ab
    st = _settle(pass_n=50, fail_n=1, info_n=1)
    assert st["info"] == 1 and sum(st["counts"].values()) == st["rows"] == 52
    assert ab.settlement_complete(st) is True
    bad = _settle(pass_n=50, fail_n=1, info_n=1, rows=53)  # 计数和 != 行数
    assert ab.settlement_complete(bad) is False


def test_ab_settlement_to_summary_integration(tmp_path, monkeypatch):
    """集成：真实结果行 → settlement() → write_outputs() → 读回 summary.md/results.json。"""
    from driver import a_baseline as ab
    from driver import infra as I

    class FakeRows:
        def __init__(self, rows):
            self.rows = rows

        def count(self, status):
            return sum(1 for r in self.rows if r["status"] == status)

    def make_rows(*statuses):
        return [{"id": f"X-{i}", "title": f"t{i}", "status": s, "command": "cmd", "rc": "0",
                 "excerpt": ""} for i, s in enumerate(statuses)]

    def run_case(statuses, extra=()):
        R = FakeRows(make_rows(*statuses))
        monkeypatch.setattr(ab, "R", R)
        monkeypatch.setattr(ab, "REPORTS", tmp_path / "reports")
        ev = tmp_path / ("ev-" + "_".join(statuses) + ("-x" if extra else ""))
        I.set_output_mode(True, formal_dir=ev, reports=tmp_path)
        ids = [r["id"] for r in R.rows]
        settle = ab.settlement(expected=frozenset(ids) | set(extra))
        rc = ab.final_exit(True, settle)
        ab.write_outputs(True, settle, rc)
        return rc, (ev / "summary.md").read_text(encoding="utf-8"), \
            json.loads((ev / "results.json").read_text(encoding="utf-8"))

    rc, text, res = run_case(["PASS", "PASS"])
    assert rc == 0 and "结论：通过" in text and "未通过" not in text
    assert res["counts"]["pass"] == 2 and res["final_exit"] == 0
    rc, text, _ = run_case(["PASS", "FAIL"])
    assert rc == 1 and "未通过" in text
    rc, text, _ = run_case(["PASS", "BLOCKED"])
    assert rc == 1 and "未通过" in text, "BLOCKED 结算完整也不得称通过"
    rc, text, res = run_case(["PASS", "INFO"])
    assert rc == 0 and "通过（附条件）" in text and "INFO" in text
    rc, text, _ = run_case(["PASS"], extra=("MISSING-1",))
    assert rc == 4 and "未通过" in text
    I.set_output_mode(True)


def test_ab_expected_checks_cover_all_items():
    from driver import a_baseline as ab
    assert len(ab.EXPECTED_CHECKS) >= 40
    for cid in ("AB-01a", "AB-02d", "AB-05f", "AB-06d", "AB-10c", "N2-http",
                "N3-media", "CLEANUP", "CLEANUP-ports"):
        assert cid in ab.EXPECTED_CHECKS, cid


def test_ab_diagnostic_mode_writes_reports_only(tmp_path, monkeypatch):
    from driver import a_baseline as ab

    class FakeRows:
        rows: list = []

        @staticmethod
        def count(_status: str) -> int:
            return 0

    monkeypatch.setattr(ab, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(ab, "R", FakeRows())
    ab.write_outputs(False, _settle(pass_n=0, expected=1, rows=0, missing=["AB-01a"]), 0)
    assert (tmp_path / "reports" / "results.json").exists()
    assert not (tmp_path / "evidence").exists(), "诊断模式绝不写/覆盖 evidence 正式路径"


# ---------- 第六轮：N2-http 判定 / requestId / 输出目录隔离 ----------

def test_n2_http_verdict_never_passes_error_paths():
    from driver import a_baseline as ab
    job = "11111111-1111-4111-8111-111111111111"
    marker = "Bearer SECRET"
    for status in (400, 401, 403, 404, 500, 503):
        v, why = ab.n2_http_verdict(status, job, {}, marker)
        assert v is not True, f"HTTP {status} 不得 PASS：{why}"
    assert ab.n2_http_verdict(200, job, {"data": {"jobId": "other"}}, marker)[0] is False
    assert ab.n2_http_verdict(200, job, {"data": {"jobId": job}}, marker)[0] is not True  # 缺字段
    assert ab.n2_http_verdict(200, job, {"data": {"jobId": job, "lastError": None}},
                              marker)[0] is True
    assert ab.n2_http_verdict(200, job, {"data": {"jobId": job,
                              "lastError": {"message": marker}}}, marker)[0] is False
    assert ab.n2_http_verdict(200, job, {"data": {"jobId": job,
                              "lastError": {"m": "L" * 4000}}}, marker)[0] is False
    assert ab.n2_http_verdict(200, job, {"data": {"jobId": job,
                              "lastError": {"code": "X"}}}, marker)[0] is True


def test_request_id_ok_rejects_missing_or_mismatch():
    from driver import a_baseline as ab
    assert ab.request_id_ok("r", {"requestId": "r"}) is True
    assert ab.request_id_ok(None, None) is False
    assert ab.request_id_ok(None, {"requestId": "r"}) is False
    assert ab.request_id_ok("r", {}) is False
    assert ab.request_id_ok("", {"requestId": ""}) is False
    assert ab.request_id_ok("r", {"requestId": "s"}) is False


def _tree_hash(root: pathlib.Path) -> str:
    h = hashlib.sha256()
    if not root.exists():
        return h.hexdigest()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_diagnostic_mode_never_touches_formal_evidence(tmp_path):
    from driver import a_baseline as ab
    real_formal = ab.I.FORMAL_EVIDENCE
    before = _tree_hash(real_formal)
    ab.I.set_output_mode(False, reports=tmp_path)
    try:
        ab.I.evidence_text("diag-only.txt", "x")
        ab.save_log_excerpts()
        assert (tmp_path / ab.I.RUN_ID / "logs" / "diag-only.txt").exists()
        assert _tree_hash(real_formal) == before, "诊断模式不得改动正式 evidence"
    finally:
        ab.I.set_output_mode(True)


def test_formal_mode_targets_formal_evidence():
    from driver import a_baseline as ab
    out = ab.I.set_output_mode(True)
    assert out["evidence"] == ab.I.FORMAL_EVIDENCE
    assert out["logs"] == ab.I.FORMAL_EVIDENCE / "logs"


# ---------- 第七轮：锁语义 / 判定措辞边界 ----------

def test_lock_excludes_second_holder_and_release_keeps_file():
    from driver import infra as I
    I.release_single_instance_lock()  # 清理可能残留的持有
    ok, why = I.acquire_single_instance_lock()
    assert ok, why
    h = open(I.LOCK_FILE, "a+", encoding="utf-8")  # 第二个 open file description
    try:
        with pytest.raises(OSError):
            fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        h.close()
    assert I.LOCK_FILE.exists()
    I.release_single_instance_lock()
    assert I.LOCK_FILE.exists(), "释放锁不得删除锁文件（否则破坏单实例保证）"
    ok2, why2 = I.acquire_single_instance_lock()
    assert ok2, why2
    I.release_single_instance_lock()


def test_n2_http_verdict_wording_boundaries():
    from driver import a_baseline as ab
    job = "j1"
    _, why_null = ab.n2_http_verdict(200, job, {"data": {"jobId": job, "lastError": None}})
    assert "本样本" in why_null
    _, why_ok = ab.n2_http_verdict(200, job,
                                   {"data": {"jobId": job, "lastError": {"code": "X"}}}, "M")
    assert "不构成通用脱敏保证" in why_ok
    _, why_missing = ab.n2_http_verdict(200, job, {"data": {"jobId": job}})
    assert "保守" in why_missing and "BLOCKED" in why_missing


# ---------- 第九轮：RV jobId 关联判定 + RV-5 INFO 语义 + 哨兵绑定 ----------

def test_rv_projection_verdict_requires_jobid_match():
    from driver import a_reverify as rv
    job = "job-1"
    assert rv.proj_verdict(200, job, {"data": {"jobId": "other", "lastError": None}}, "M")[0] is False
    assert rv.proj_verdict(200, job, {"data": {"lastError": None}}, "M")[0] is not True
    assert rv.proj_verdict(200, job, {"data": {"jobId": job}}, "M")[0] is not True
    assert rv.proj_verdict(200, job, {"data": {"jobId": job,
                              "lastError": {"reason": "internal", "retryable": True}}}, "M")[0] is True
    assert rv.proj_verdict(200, job, {"data": {"jobId": job,
                              "lastError": {"reason": "E_DIAG_MARKER", "retryable": True}}}, "M")[0] is False
    assert rv.proj_verdict(200, job, {"data": {"jobId": job, "lastError": {
        "reason": "internal", "retryable": True, "message": "x"}}}, "M")[0] is False


def test_rv_queued_verdict_explicit_null_and_jobid():
    from driver import a_reverify as rv
    job = "j"
    ok = {"data": {"jobId": job, "status": "queued", "lastError": None, "finishedAt": None}}
    assert rv.queued_verdict(200, job, ok)[0] is True
    assert rv.queued_verdict(200, job, {"data": {"jobId": job, "status": "queued",
                              "lastError": None}})[0] is False          # 缺 finishedAt 字段
    assert rv.queued_verdict(200, job, {"data": {"jobId": "x", "status": "queued",
                              "lastError": None, "finishedAt": None}})[0] is False
    assert rv.queued_verdict(200, job, {"data": {"jobId": job, "status": "succeeded",
                              "lastError": None, "finishedAt": None}})[0] is False


def test_rv5_verdict_info_not_unconditional_pass():
    from driver import a_reverify as rv
    assert rv.rv5_verdict(False, True, True, 200, True)[0] is False   # 同账号 → FAIL
    assert rv.rv5_verdict(True, False, True, 200, True)[0] is False   # 会话无效
    assert rv.rv5_verdict(True, True, True, 200, True)[0] is None     # 跨账号可读 → INFO 待裁定
    assert rv.rv5_verdict(True, True, True, 404, True)[0] is None     # 被拒 → INFO 待裁定
    assert rv.rv5_verdict(True, True, True, 500, False)[0] is False   # 非法形态


def test_reverify_sentinel_bound_to_run(tmp_path):
    from driver import verify_reverify_sentinel as vs
    good = {"counts": {"pass": 10, "fail": 0, "blocked": 0, "info": 1},
            "missing": [], "extra": [], "duplicates": [], "unknown_status": [],
            "rows": 11, "settled": 11}
    vs.write_sentinel("run-1", good, 0, reports_dir=tmp_path)
    assert vs.verify("run-1", reports_dir=tmp_path)[0] is True
    assert vs.verify("run-1", reports_dir=tmp_path, driver_rc=0)[0] is True
    assert vs.verify("run-1", reports_dir=tmp_path, driver_rc=1)[0] is False   # 哨兵 exit0 != 驱动 rc1
    assert vs.verify("run-2", reports_dir=tmp_path)[0] is False               # 错 run_id
    vs.write_sentinel("run-3", {**good, "missing": ["RV-9"], "settled": 10, "rows": 10}, 4,
                      reports_dir=tmp_path)
    assert vs.verify("run-3", reports_dir=tmp_path)[0] is False               # 缺项
    vs.write_sentinel("run-4", {**good, "counts": {"pass": 9, "fail": 0, "blocked": 0,
                                                   "info": 1}}, 0, reports_dir=tmp_path)
    assert vs.verify("run-4", reports_dir=tmp_path)[0] is False               # 计数和!=rows
    bad5 = {**good, "counts": {"pass": 10, "fail": 1, "blocked": 0, "info": 0},
            "settled": 11, "rows": 11}
    vs.write_sentinel("run-5", bad5, 0, reports_dir=tmp_path)
    assert vs.verify("run-5", reports_dir=tmp_path)[0] is False               # final_exit 与政策不一致


def test_reverify_entry_binding_rejects_old_sentinel(tmp_path):
    """入口级负例：旧哨兵存在但本次 RUN_ID 未写哨兵 → 拒绝（不得 OK）。"""
    from driver import verify_reverify_sentinel as vs
    good = {"counts": {"pass": 10, "fail": 0, "blocked": 0, "info": 1},
            "missing": [], "extra": [], "duplicates": [], "unknown_status": [],
            "rows": 11, "settled": 11}
    vs.write_sentinel("old-run", good, 0, reports_dir=tmp_path)   # 上次成功运行遗留
    ok, msg = vs.verify("new-run", reports_dir=tmp_path, driver_rc=0)
    assert ok is False and "缺失" in msg, "本次未写哨兵时不得对旧 run 判 OK"
    # 旧哨兵 rc 与本次驱动 rc 不一致 → 拒绝
    vs.write_sentinel("old-run2", good, 1, reports_dir=tmp_path)
    ok2, msg2 = vs.verify("old-run2", reports_dir=tmp_path, driver_rc=0)
    assert ok2 is False and "final_exit" in msg2


# ---------- RV-5 有界复验：参数化哨兵 + 结论政策 ----------

def test_sentinel_mode_parameterized(tmp_path):
    from driver import verify_reverify_sentinel as vs
    settle = {"counts": {"pass": 10, "fail": 0, "blocked": 0, "info": 0},
              "missing": [], "extra": [], "duplicates": [], "unknown_status": [],
              "rows": 10, "settled": 10}
    vs.write_sentinel("rv5-run", settle, 0, reports_dir=tmp_path, mode="rv5-reverify",
                      expected=vs.EXPECTED_RV5)
    assert vs.verify("rv5-run", reports_dir=tmp_path, driver_rc=0, mode="rv5-reverify",
                     expected=vs.EXPECTED_RV5)[0] is True
    assert vs.verify("rv5-run", reports_dir=tmp_path, mode="targeted-reverify",
                     expected=vs.EXPECTED_TARGETED)[0] is False   # mode/expected 不符


def test_rv5_three_state_and_collision_negative_cases():
    from driver import a_rv5 as r5
    e = {"requestId": "r1", "error": {"code": "RESOURCE_NOT_VISIBLE", "message": "job not visible"}}
    e2 = {"requestId": "r2", "error": {"code": "RESOURCE_NOT_VISIBLE", "message": "job not visible"}}
    # 仅排除 requestId：逐请求字段不同仍等值
    assert r5.canon_public(e) == r5.canon_public(e2)
    # 某一态多出顶层 data / 其他公开字段 → 不等值 → 不得 PASS
    extra = {**e, "data": {"jobId": "leak"}}
    assert r5.canon_public(extra) != r5.canon_public(e)
    assert r5.three_state_ok([r5.canon_public(e), r5.canon_public(e2),
                              r5.canon_public(extra)], [], True, True) is False
    # 三态 error message 不一致 → 不得 PASS
    diff_msg = {"requestId": "r3", "error": {"code": "RESOURCE_NOT_VISIBLE", "message": "other"}}
    assert r5.three_state_ok([r5.canon_public(e), r5.canon_public(e2),
                              r5.canon_public(diff_msg)], [], True, True) is False
    # 种子失败 → 不得 PASS
    assert r5.three_state_ok([r5.canon_public(e)] * 3, [], False, True) is False
    # 禁止内容命中 → 不得 PASS
    assert r5.three_state_ok([r5.canon_public(e)] * 3, ["app_account"], True, True) is False
    # happy
    assert r5.three_state_ok([r5.canon_public(e), r5.canon_public(e2),
                              r5.canon_public(e)] * 1, [], True, True) is True
    # POST 碰撞：keyed 响应附顶层 data 含外来 jobId → 不得 PASS
    leak = {**e, "data": {"jobId": "foreign"}}
    canon_bad = [r5.canon_public(e), r5.canon_public(leak), r5.canon_public(e), r5.canon_public(e)]
    assert r5.post_collision_ok(canon_bad, [], "rejected|RESOURCE_NOT_VISIBLE",
                                "rejected|RESOURCE_NOT_VISIBLE", True, "0", True) is False
    # 重放后 T13 翻 succeeded → 不得 PASS
    assert r5.post_collision_ok([r5.canon_public(e)] * 4, [], "rejected|RESOURCE_NOT_VISIBLE",
                                "succeeded|", True, "0", True) is False
    # 禁止内容命中 → 不得 PASS
    assert r5.post_collision_ok([r5.canon_public(e)] * 4, ["foreign"], "rejected|RESOURCE_NOT_VISIBLE",
                                "rejected|RESOURCE_NOT_VISIBLE", True, "0", True) is False
    # happy（四条完整拒绝体等值 + T13 首/重放 rejected + 行不变 + 无 B 行 + 正例）
    assert r5.post_collision_ok([r5.canon_public(e)] * 4, [], "rejected|RESOURCE_NOT_VISIBLE",
                                "rejected|RESOURCE_NOT_VISIBLE", True, "0", True) is True
    assert r5.forbidden_hit("has APP_ACCOUNT inside", ["app_account"]) == ["app_account"]


def test_rv5_conclusion_policy():
    from driver import a_rv5 as r5

    def st(p=0, f=0, b=0, i=0, missing=()):
        counts = {"pass": p, "fail": f, "blocked": b, "info": i}
        return {"counts": counts, "pass": p, "fail": f, "blocked": b, "info": i,
                "expected": 10, "settled": p + f + b + i, "rows": p + f + b + i,
                "missing": list(missing), "extra": [], "duplicates": [], "unknown_status": []}

    assert "通过（附条件）" in r5.rv5_conclusion(st(p=9, i=1))
    assert "未通过" in r5.rv5_conclusion(st(p=9, f=1))
    assert "未通过" in r5.rv5_conclusion(st(p=9, b=1))
    assert "未通过" in r5.rv5_conclusion(st(p=9, missing=["RV5-3"]))
    assert "拒绝" in r5.rv5_conclusion({**st(p=9), "unknown_status": ["X"]})


# ---------- C 验收驱动：CC-02/CC-03 回归锁定 ----------

def test_cc02_other_active_grant_must_be_200():
    """CC-02 唯一曾写反的谓词：另一仍 active 的授权账号必须 200（非 404）。"""
    from driver import c_care

    base = dict(statuses=[404] * 6, canon=["{}"] * 6,
                codes=["RESOURCE_NOT_VISIBLE"] * 6, c403=403,
                b403={"error": {"code": "CALLER_NOT_ALLOWED"}}, c401=401, cA=200, cB=404)
    ok, flags = c_care.cc02_verdict(cC=200, **base)
    assert ok is True and flags["cC"] is True          # active 授权 → 200 判通过
    ok2, flags2 = c_care.cc02_verdict(cC=404, **base)
    assert ok2 is False and flags2["cC"] is False      # 若再误写 404 → 必须 FAIL
    # 其余既有断言不得因修谓词被弱化
    for key, bad in (("statuses", [200] * 6), ("codes", ["NOT_FOUND"] * 6),
                     ("cA", 404), ("cB", 200)):
        kw = {**base, "cC": 200, key: bad}
        assert c_care.cc02_verdict(**kw)[0] is False, key


def test_cc03_variant_env_explicit_and_isolated():
    """CC-03 启动封装：逐变体三键显式构造，不依赖继承/残留（防正例 503 回归）。"""
    from driver import c_care

    m = "11111111-1111-4111-8111-111111111111"
    dev = c_care.variant_env(profiles="dev", bound_member=m)
    prod = c_care.variant_env(profiles="prod")
    mixed = c_care.variant_env(profiles="prod,dev", bound_member=m)
    penv = c_care.variant_env(profiles="dev", bound_member=m, app_env="production")
    bad = c_care.variant_env(profiles="dev", bound_member="not-a-uuid")
    keys = {"SPRING_PROFILES_ACTIVE", "APP_C_FACE_BOUND_MEMBER", "APP_ENV"}
    for env in (dev, prod, mixed, penv, bad):
        assert set(env) == keys, env
    assert dev["SPRING_PROFILES_ACTIVE"] == "dev" and dev["APP_C_FACE_BOUND_MEMBER"] == m
    assert prod["APP_C_FACE_BOUND_MEMBER"] == ""       # 无绑定变体显式清空，防继承污染
    assert mixed["SPRING_PROFILES_ACTIVE"] == "prod,dev" and mixed["APP_C_FACE_BOUND_MEMBER"] == m
    assert penv["APP_ENV"] == "production" and penv["SPRING_PROFILES_ACTIVE"] == "dev"
    assert bad["APP_C_FACE_BOUND_MEMBER"] == "not-a-uuid"
    assert dev["APP_ENV"] == ""                        # 非 production 显式置空


# ---------- C 验收驱动：R14 加强断言负例回归 ----------

def test_cc03_unrelated_startup_failure_must_not_pass():
    """CC-03：无关原因退出（构建/DB/端口/成功启动）不得冒充生产拒绝。"""
    from driver import c_care

    assert c_care.cc03_failfast_reason("prod-only", "java.lang.OutOfMemoryError") == \
        (False, "no_production_signature")
    assert c_care.cc03_failfast_reason(
        "prod-only", "Started WebJavaApplication\nProductionFailClosedValidator")[0] is False
    assert c_care.cc03_failfast_reason(
        "prod-only", "APPLICATION FAILED TO START: No qualifying bean of type SessionProvider")[0] \
        is True
    assert c_care.cc03_failfast_reason(
        "dev+APP_ENV=production", "ProductionFailClosedValidator production fail-closed")[0] is True
    assert c_care.cc03_failfast_reason("dev+APP_ENV=production", "OutOfMemoryError")[0] is False
    assert c_care.cc03_failfast_reason(
        "dev+invalid-bound", "MemberBindingFaceDouble must be a UUID or blank: x")[0] is True
    assert c_care.cc03_failfast_reason("dev+invalid-bound", "APPLICATION FAILED TO START")[0] is False


def test_cc05_any_landing_or_empty_body_must_not_pass():
    """CC-05：任一落点非期望状态或空体/快照不满足 → 不得 PASS。"""
    from driver import c_care

    good = dict(hit=[], no_schema_version=True, vd_ok=True, regions_kept=True, full_kept=True,
                a01_sum_ok=True, proj_ok=True, snap_ok=True, a09_ok=True)
    ok_land = {"A01": 200, "A02": 200, "A03": 201, "A08": 200, "A09": 200}
    assert c_care.cc05_verdict(ok_land, **good) is True
    for bad in ok_land:
        st = dict(ok_land)
        st[bad] = 500 if bad != "A03" else 200
        assert c_care.cc05_verdict(st, **good) is False, bad
    assert c_care.cc05_verdict(ok_land, **{**good, "vd_ok": False}) is False
    assert c_care.cc05_verdict(ok_land, **{**good, "snap_ok": False}) is False
    assert c_care.cc05_verdict(ok_land, **{**good, "hit": ["provider_raw_response"]}) is False


def test_cc06_requires_exact_409_and_token():
    """CC-06：非 409 或 token 不精确（含前缀匹配）不得计为畸形拒绝。"""
    from driver import c_care

    assert c_care.cc06_variant_ok(
        409, "PLAN_NOT_READY", "region_not_supported", "region_not_supported") is True
    assert c_care.cc06_variant_ok(200, "", "", "malformed_frozen_capability") is False
    assert c_care.cc06_variant_ok(
        409, "PLAN_NOT_READY", "region_not_supported", "malformed_frozen_capability") is False
    assert c_care.cc06_variant_ok(
        409, "INVALID_INPUT", "malformed_frozen_capability",
        "malformed_frozen_capability") is False


def test_cc09_empty_duplicate_must_not_pass():
    """CC-09：空 disp（all([])==True）不得 PASS；K 边界不满足不得 PASS。"""
    from driver import c_care

    base = dict(k9_ok=True, k10_ok=True, k11_ok=True, gating_ok=True, conflict_ok=True,
                stopped_ok=True, overflow_ok=True)
    assert c_care.cc09_verdict(dup_ok=True, **base) is True
    assert c_care.cc09_verdict(dup_ok=False, **base) is False
    assert c_care.cc09_verdict(dup_ok=True, **{**base, "k11_ok": False}) is False
    assert c_care.cc09_verdict(dup_ok=True, **{**base, "overflow_ok": False}) is False


def test_cc10_new_key_replay_must_not_claim_manifest_unchanged():
    """CC-10：新键重放/未关/缺口未覆盖 → 不得宣称重放 manifest 不变或闭合。"""
    from driver import c_care

    good = dict(stop_ok=True, gaps_ok=True, one_ok=True, closed=True, occ_rel=True,
                replay_ok=True, freeze_ok=True, late_ok=True, ack_ok=True, still_close=True,
                minimal=True, get_2xx=True)
    assert c_care.cc10_verdict(**good) is True
    assert c_care.cc10_verdict(**{**good, "replay_ok": False}) is False
    assert c_care.cc10_verdict(**{**good, "gaps_ok": False}) is False
    assert c_care.cc10_verdict(**{**good, "closed": False}) is False


def test_cc11_missing_strict_validation_must_not_pass():
    """CC-11：缺捕获或任一 API 严格校验失败 → 不得 PASS。"""
    from driver import c_care

    assert c_care.cc11_verdict(True, 9, [], []) is True
    assert c_care.cc11_verdict(True, 9, [], ["A01:missing required"]) is False
    assert c_care.cc11_verdict(True, 8, [], []) is False
    assert c_care.cc11_verdict(False, 9, [], []) is False
    assert c_care.cc11_verdict(True, 9, ["A03=500"], []) is False


# ---------- CD-chain 验收驱动回归 ----------

def test_cd_chain_sentinel_mode_and_expected(tmp_path):
    """cd-chain 哨兵：EXPECTED_CD 10 项、mode 绑定、错 mode 必须拒绝。"""
    from driver import verify_reverify_sentinel as vs

    assert len(vs.EXPECTED_CD) == 10
    assert "CD-01" in vs.EXPECTED_CD and "CD-08" in vs.EXPECTED_CD
    assert "CLEANUP" in vs.EXPECTED_CD and "CLEANUP-ports" in vs.EXPECTED_CD
    settle = {"counts": {"pass": 10, "fail": 0, "blocked": 0, "info": 0}, "settled": 10,
              "expected": 10, "rows": 10, "missing": [], "extra": [], "duplicates": [],
              "unknown_status": []}
    vs.write_sentinel("E-CD-test", settle, 0, reports_dir=tmp_path, mode="cd-chain",
                      expected=vs.EXPECTED_CD)
    ok, _ = vs.verify("E-CD-test", reports_dir=tmp_path, driver_rc=0, mode="cd-chain",
                      expected=vs.EXPECTED_CD)
    assert ok is True
    bad, why = vs.verify("E-CD-test", reports_dir=tmp_path, driver_rc=0, mode="c-care",
                         expected=vs.EXPECTED_C)
    assert bad is False and "mode" in why          # 错 mode 拒绝
    rc_bad, _ = vs.verify("E-CD-test", reports_dir=tmp_path, driver_rc=1, mode="cd-chain",
                          expected=vs.EXPECTED_CD)
    assert rc_bad is False                          # final_exit==驱动 rc


def test_cd_conclusion_policy():
    """CD-chain 结论政策：FAIL/BLOCKED/缺项/未知状态不通过；全 PASS 完整才通过。"""
    from driver import cd_chain

    def st(p=0, f=0, b=0, i=0, missing=()):
        counts = {"pass": p, "fail": f, "blocked": b, "info": i}
        return {"counts": counts, "settled": p + f + b + i, "expected": 10,
                "rows": p + f + b + i, "missing": list(missing), "extra": [],
                "duplicates": [], "unknown_status": []}

    assert "未通过" in cd_chain.cd_conclusion(st(p=9, f=1))
    assert "未通过" in cd_chain.cd_conclusion(st(p=9, b=1))
    assert "未通过" in cd_chain.cd_conclusion(st(p=9, missing=["CD-3"]))
    assert "拒绝" in cd_chain.cd_conclusion({**st(p=9), "unknown_status": ["X"]})
    assert "通过" in cd_chain.cd_conclusion(st(p=10))


def test_cd01_binding_is_ancestry_not_head_equality():
    """CD-01 绑定=祖先关系+业务路径 diff 空；HEAD 前移（仅 E 提交）不得 FAIL。"""
    from driver import cd_chain

    base = dict(anc_c=True, anc_d=True, anc_merged=True, business_diff=[],
                care_files=[], contract_files=[], mvn_rc=0, venv_ok=True, health_up=True)
    assert cd_chain.cd01_binding_ok(**base) is True
    # 负例 1：merged..HEAD 业务路径非空 diff → 必须 FAIL
    assert cd_chain.cd01_binding_ok(
        **{**base, "business_diff": ["M\tbackend/web-java/src/x.java"]}) is False
    # 负例 2：merged 非当前 HEAD 祖先 → 必须 FAIL
    assert cd_chain.cd01_binding_ok(**{**base, "anc_merged": False}) is False
    # 负例 3：C/D 非祖先 / 既有 care、contracts diff 回归 → 必须 FAIL
    assert cd_chain.cd01_binding_ok(**{**base, "anc_c": False}) is False
    assert cd_chain.cd01_binding_ok(**{**base, "anc_d": False}) is False
    assert cd_chain.cd01_binding_ok(**{**base, "care_files": ["M\tcare/x.java"]}) is False
    assert cd_chain.cd01_binding_ok(**{**base, "contract_files": ["M\tcontracts/x"]}) is False


def test_cc11_strict_oas_semantics_and_discrimination():
    """CC-11 严格语义：nullable over $ref/allOf 拒绝 null、allOf 不展平；状态/实现缺陷→FAIL。"""
    from driver import c_care

    doc = {"components": {"schemas": {"X": {
        "type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"],
        "additionalProperties": False}}}}
    node_null = {"allOf": [{"$ref": "#/components/schemas/X"}], "nullable": True}
    errs_null = c_care.oas_errors_node(node_null, doc, None)
    assert errs_null                                        # 旧 nullable 形状必须拒绝 null
    # allOf 不展平：兄弟分支新增属性仍被 X 的 additionalProperties:false 拒绝
    node_allof = {"allOf": [{"$ref": "#/components/schemas/X"},
                            {"type": "object", "properties": {"b": {"type": "string"}}}]}
    assert c_care.oas_errors_node(node_allof, doc, {"a": "x", "b": "y"})
    assert not c_care.oas_errors_node({"$ref": "#/components/schemas/X"}, doc, {"a": "x"})
    # 结论政策：状态不符/实现缺陷→FAIL；仅契约建模→INFO；全过→PASS
    assert c_care.cc11_outcome(True, 9, [], [], []) == "PASS"
    assert c_care.cc11_outcome(True, 9, ["A03=200 not in (201,)"], [], []) == "FAIL"
    assert c_care.cc11_outcome(True, 9, [], ["A01 $: enum violated"], []) == "FAIL"
    assert c_care.cc11_outcome(
        True, 9, [], [], ["A03 $.data.x [contract:nullable-over-$ref/allOf]"]) == "INFO"
    assert c_care.cc11_outcome(True, 8, [], [], []) == "FAIL"


def _cc11_synth_errors(api, node, doc, body):
    from driver import c_care
    return [(e, c_care.classify_strict_error(api, e))
            for e in c_care.oas_errors_node(node, doc, body)]


def test_cc11_a08_unknown_field_set_and_schema_path_binding():
    """D1 收敛后判别：A08 干净响应无 additionalProperties 错误；任意未知字段→impl。"""
    import pathlib
    import yaml
    from driver import c_care

    doc = yaml.safe_load((pathlib.Path(c_care.I.CONTRACTS) / "openapi" / "openapi.yaml")
                         .read_text("utf-8"))
    node_a08 = doc["paths"]["/api/v1/care-plans/{planId}/progress"]["get"]["responses"]["200"][
        "content"]["application/json"]["schema"]
    data_clean = {"targetCount": "3", "completedCount": "1", "remainingCount": "2",
                  "isCompleted": False, "progressRevision": "1", "completedAt": None,
                  "lastSyncedAt": "2026-01-01T00:00:00Z"}
    errs_clean = [e for e in c_care.oas_errors_node(node_a08, doc, {"data": data_clean})
                  if e.validator == "additionalProperties"]
    assert errs_clean == []  # 展平后 lastSyncedAt 已声明 → 无 additionalProperties 错误
    # 任意额外未知字段（含引号字段名 / 多字段）→ allowlist 已空 → 一律 impl FAIL
    for extra in ({"secret": "LEAK"}, {"secret'x": "LEAK"}, {'sec"y': "LEAK"},
                  {"a1": "L", "a2": "L"}):
        errs = [e for e in c_care.oas_errors_node(node_a08, doc, {"data": {**data_clean, **extra}})
                if e.validator == "additionalProperties"]
        assert errs, extra
        assert c_care.classify_strict_error("A08", errs[0]) == "impl-or-other", extra


def test_cc11_allowlist_precise_no_impl_downgrade():
    """D1 收敛：allowlist 空表；schema path 不符 / 收 null / 普通 additionalProperties→impl FAIL。"""
    from driver import c_care

    assert c_care.CC11_CONTRACT_ALLOWLIST == {}, c_care.CC11_CONTRACT_ALLOWLIST
    # 1) 曾为契约缺陷的 nullable-over-$ref 形状（收 null）→ 收敛后一律 impl FAIL
    doc2 = {"components": {"schemas": {"P": {
        "type": "object", "additionalProperties": False,
        "properties": {"completedAt": {"type": "string"}}, "required": ["completedAt"]}}}}
    node2 = {"type": "object", "properties": {"data": {"type": "object", "properties": {
        "progress": {"$ref": "#/components/schemas/P"}}}}}
    e2 = [e for e in c_care.oas_errors_node(node2, doc2, {"data": {"progress": {"completedAt": None}}})
          if e.validator == "type"][0]
    assert c_care.normalize_json_path(e2.json_path) == "$.data.progress.completedAt"
    assert c_care.classify_strict_error("A02", e2) == "impl-or-other"
    # 2) 普通 additionalProperties:false 出现未声明字段 → impl
    node3 = {"$ref": "#/components/schemas/P"}
    e3 = [e for e in c_care.oas_errors_node(node3, doc2, {"completedAt": "x", "b": "y"})
          if e.validator == "additionalProperties"][0]
    assert c_care.classify_strict_error("A08", e3) == "impl-or-other"
    # 3) allowlist 外路径 → impl
    assert c_care.classify_strict_error("A09", e2) == "impl-or-other"


def test_d1_periodic_and_logout_semantics():
    """D1 回归：常驻周期日志判定 + 登出代次同事务语义（纯函数）。"""
    from framework import live

    assert live.log_has_text("x scanner.task_ran task=incident.scan y", "incident.scan")
    assert live.log_has_text("task=media.cleanup.discover", "media.cleanup.discover")
    assert not live.log_has_text("no marker", "incident.scan")
    assert live.logout_revision_ok("invalid", 2, 1, "2026-01-01T00:00:00Z", True) is True
    assert live.logout_revision_ok("invalid", 1, 1, "", True) is False      # 未 +1 / 无 invalidated_at
    assert live.logout_revision_ok("active", 2, 1, "t", True) is False     # 未失效
    assert live.logout_revision_ok("invalid", 2, 1, "t", False) is False   # 重复登出不幂等


def test_cd03_expected_baseline_precise_values():
    """CD-03 精确基线：ranges_match 严判 unit/min/max，常量与 D 受控基线一致。"""
    from driver import cd_chain

    assert cd_chain.ranges_match(
        {"intensity": {"unit": "percent", "min": 0.0, "max": 100.0}},
        {"intensity": {"unit": "percent", "min": 0.0, "max": 100.0}}) is True
    assert cd_chain.ranges_match(
        {"intensity": {"unit": "percent", "min": 0.0, "max": 99.0}},
        cd_chain.EXPECTED_RANGES) is False
    assert cd_chain.ranges_match(
        {"intensity": {"unit": "kg", "min": 0.0, "max": 100.0}},
        cd_chain.EXPECTED_RANGES) is False
    assert cd_chain.EXPECTED_CAP_ID == "mvp-double-capability"
    assert cd_chain.EXPECTED_REGIONS == {"forehead", "left_cheek", "right_cheek", "nose"}
    assert cd_chain.EXPECTED_N_BOUNDS == {"min": 1, "max": 100}
    assert cd_chain.EXPECTED_TARGET == 30


def test_cd06_enroll_bound_to_chain_not_earliest():
    """CD-06：enroll 必须为本链新增；预存无关 succeeded enroll + 本链缺失 → 绑定空 → 不得 PASS。"""
    from driver import cd_chain

    assert cd_chain.new_job_ids({"old"}, ["old"]) == []          # 本链 enroll 缺失 → 空
    assert cd_chain.new_job_ids({"old"}, ["old", "new"]) == ["new"]
    assert cd_chain.new_job_ids(set(), ["a", "b"]) == ["a", "b"]
    assert cd_chain.new_job_ids({"a", "b"}, ["a", "b", "a"]) == []  # 预存顶替不算新增
