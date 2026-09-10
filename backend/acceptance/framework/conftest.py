# -*- coding: utf-8 -*-
"""E 验收 pytest 插件：marker 注册、基线门控统计、场景结算守卫、证据强制、退出码。

由 backend/acceptance/conftest.py 经 pytest_plugins 加载（顶层 conftest 合法），
PYTEST_ADDOPTS/--ignore 只影响收集，不影响本插件的结算守卫。

规则：
- 场景测试在 gate=closed 时 skip，reason 前缀固定 ``dependency_pending: ``；与普通
  skipped 分开统计。
- passed 绑定证据（所有模式生效）：任何带 sc_id 的测试在 call 阶段 passed 时，必须
  已通过 scenario_evidence 夹具记录 ≥1 条 HTTP 证据并封存替身声明，否则插件把该
  报告改判 failed（"pass without evidence"），防止裸通过。
- 模式来自 E_ACCEPTANCE_MODE（run.sh 注入）：
    selfcheck → 框架自检，退出码保持 pytest 原生 0/1；
    matrix（未注入时的默认，fail-safe）→ 强制结算守卫：
      matrix/scenarios.json 的全部 94 个 sc_id 必须各恰好结算一次（passed /
      dependency_pending / failed）；缺失、未收集、被 deselect、重复异常，或存在
      普通 skipped（SKIPPED_OTHER>0）→ 退出码 4（结算不完整，绝不 0）；
      结算完整后：有 failed → 1；仍有 dependency_pending → 3；全通过 → 0。
- 汇总行固定输出 PASSED/DEPENDENCY_PENDING/FAILED/SKIPPED_OTHER 与
  SETTLED、EVIDENCE_TAGS 分类计数。
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest

from framework import isolation
from framework.client import EvidenceRecorder
from framework.doubles import DoublesManifest
from framework.gate import PENDING_PREFIX, ROOT, SCENARIOS_PATH

MARKERS = (
    ("sc_id", "场景编号标记，如 sc_id('SC-00-01')"),
    ("priority", "清单优先级 P0/P1"),
    ("scope", "验证范围：后端/集成/联调"),
    ("package", "负责业务工作包：B/C/D（可重复标记）"),
    ("deps", "开发对接项 D01-D08（可重复标记）"),
)

EXIT_SETTLEMENT_INCOMPLETE = 4


class _State:
    def __init__(self) -> None:
        self.mode = os.environ.get("E_ACCEPTANCE_MODE", "matrix")
        self.required: set[str] = set()
        self.required_error: str | None = None
        self.duplicates: set[str] = set()
        self.deselected_scenarios: set[str] = set()
        self.settled: dict[str, str] = {}      # sc_id → passed|dependency_pending|failed
        self.settlements: dict[str, "ScenarioSettlement"] = {}
        self.counts = {"passed": 0, "failed": 0, "pending": 0, "skipped_other": 0}
        self.evidence_tags: dict[str, int] = {}
        self.run_id = ""

    def load_required(self) -> None:
        """matrix 模式的必须结算集合 = 矩阵全部场景 ID。加载失败按守卫失败处理。"""
        if self.mode != "matrix":
            return
        try:
            items = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
            ids = [s["id"] for s in items]
            assert ids, "scenarios.json 为空"
            assert len(ids) == len(set(ids)), "scenarios.json 场景 ID 重复"
            self.required = set(ids)
        except Exception as exc:  # fail-closed：矩阵不可读则无法证明结算完整
            self.required_error = f"matrix 守卫无法加载场景矩阵：{exc}"

    @staticmethod
    def sc_marker_id(item) -> str | None:
        m = item.get_closest_marker("sc_id")
        return m.args[0] if m and m.args else None

    def settle(self, sid: str, result: str) -> None:
        if sid in self.settled:
            self.duplicates.add(sid)
        self.settled[sid] = result

    def settlement_ok(self) -> tuple[bool, str]:
        if self.mode != "matrix":
            return True, ""
        if self.required_error:
            return False, self.required_error
        missing = sorted(self.required - set(self.settled))
        extra = sorted(set(self.settled) - self.required)
        problems = []
        if missing:
            problems.append(f"未结算场景 {len(missing)} 个（如 {missing[:3]}）")
        if extra:
            problems.append(f"结算了矩阵外场景 {extra[:3]}")
        if self.duplicates:
            problems.append(f"重复结算 {sorted(self.duplicates)[:3]}")
        if self.deselected_scenarios:
            problems.append(f"被 deselect 的场景 {sorted(self.deselected_scenarios)[:3]}")
        if self.counts["skipped_other"] > 0:
            problems.append(f"存在普通 skipped={self.counts['skipped_other']}（验收矩阵禁止静默跳过）")
        if problems:
            return False, "；".join(problems)
        return True, ""


def pytest_configure(config: pytest.Config) -> None:
    for name, desc in MARKERS:
        config.addinivalue_line("markers", f"{name}(value): {desc}")
    st = _State()
    st.load_required()
    try:
        st.run_id = isolation.new_run_id(os.environ.get(isolation.ENV_RUN_PREFIX, "E"))
    except Exception:  # pragma: no cover - new_run_id 自带兜底前缀
        st.run_id = "E-unassigned"
    config._e_acc = st


def _state(config) -> _State:
    return getattr(config, "_e_acc", _State())


def pytest_deselected(items) -> None:
    if not items:
        return
    st = _state(items[0].config)
    for it in items:
        sid = st.sc_marker_id(it)
        if sid:
            st.deselected_scenarios.add(sid)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    rep = outcome.get_result()
    st = _state(item.session.config)
    sid = st.sc_marker_id(item)

    # —— passed 必须绑定证据与替身声明（改判必须发生在计数之前）——
    if sid and rep.when == "call" and rep.passed:
        sm = st.settlements.get(sid)
        reason = (sm.ok_reason() if sm
                  else "场景未获得 scenario_evidence 夹具（无证据通道即视为无证据）")
        if reason:
            rep.outcome = "failed"
            rep.longrepr = (f"{item.location[0]}:{item.location[1]}: AssertionError: "
                            f"pass without evidence: {reason}")

    # —— 场景结算（skip 归类 dependency_pending；其余终判为 passed/failed）——
    if sid:
        if rep.when == "call" and rep.passed:
            st.settle(sid, "passed")
            sm = st.settlements.get(sid)
            if sm:
                tag = sm.doubles.evidence_tag()
                st.evidence_tags[tag] = st.evidence_tags.get(tag, 0) + 1
        elif rep.when == "call" and rep.failed:
            st.settle(sid, "failed")
        elif rep.when == "setup" and rep.failed:
            st.settle(sid, "failed")
        elif rep.skipped:
            st.settle(sid, "dependency_pending"
                      if PENDING_PREFIX in str(rep.longrepr or "") else "failed")

    # —— 全局计数（使用改判后的最终结论）——
    c = st.counts
    if rep.when == "call" and rep.passed:
        c["passed"] += 1
    elif rep.skipped and PENDING_PREFIX in str(rep.longrepr or ""):
        c["pending"] += 1
    elif rep.failed:
        c["failed"] += 1
    elif rep.skipped:
        c["skipped_other"] += 1


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    st = _state(config)
    c = st.counts
    ok, why = st.settlement_ok()
    terminalreporter.write_sep("=", "E 验收统计")
    terminalreporter.write_line(
        f"PASSED={c['passed']} DEPENDENCY_PENDING={c['pending']} FAILED={c['failed']} "
        f"SKIPPED_OTHER={c['skipped_other']} MODE={st.mode} RUN_ID={st.run_id}")
    terminalreporter.write_line(
        f"SETTLED={len(st.settled)}/{'94' if st.mode == 'matrix' else '-'} "
        f"EVIDENCE_TAGS no_externals={st.evidence_tags.get('no_externals', 0)} "
        f"doubles_pass={st.evidence_tags.get('doubles_pass', 0)} "
        f"mixed={st.evidence_tags.get('mixed', 0)} real_pass={st.evidence_tags.get('real_pass', 0)}")
    if st.mode == "matrix":
        if ok:
            terminalreporter.write_line(
                f"SETTLEMENT_OK: {len(st.required)}/{len(st.required)} 场景唯一结算。")
        else:
            terminalreporter.write_line(f"SETTLEMENT_INCOMPLETE: {why}")
    if c["pending"]:
        terminalreporter.write_line(
            "说明：dependency_pending = A 基线未交付导致的依赖挂起，不是通过，也不是普通跳过。")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    st = _state(session.config)
    if st.mode != "matrix":
        return  # selfcheck：保持 pytest 原生 0/1
    c = st.counts
    ok, _ = st.settlement_ok()
    if c["failed"] > 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED   # 1
    elif not ok:
        session.exitstatus = EXIT_SETTLEMENT_INCOMPLETE     # 4：零/残缺场景运行绝不假 0
    elif c["pending"] > 0:
        session.exitstatus = 3                              # 依赖挂起
    # 否则维持 0：94 全部真实通过且证据齐备


# ---------------- scenario_evidence 夹具：passed 与证据/替身声明的绑定通道 ----------------

class ScenarioSettlement:
    """单场景证据与替身声明。场景步骤作者用法（A 基线后编写步骤时）：

        def test_SC_02_01(scenario_evidence, e_client):
            se = scenario_evidence
            se.doubles.add("face_algo", "double")   # 外部依赖逐个登记 double/real
            resp = e_client.post("/api/v1/skin-assessment-tasks", ...)
            se.record_raw(method="POST", path="/api/v1/skin-assessment-tasks",
                          status=resp.status_code, request_id=resp.headers.get("X-Request-Id",""),
                          request_headers={}, request_json=None,
                          response_excerpt=resp.text[:4000], started_at=0.0, elapsed_ms=0.0)
            se.seal()                               # 必须封存；否则 passed 会被改判 fail

    无外部依赖的场景可不调用 doubles.add，但必须 seal()（证据标签记 no_externals）。
    """

    def __init__(self, scenario_id: str, recorder: EvidenceRecorder) -> None:
        self.scenario_id = scenario_id
        self.recorder = recorder
        self.doubles = DoublesManifest(scenario_id)
        self._sealed = False

    def record_raw(self, **entry) -> None:
        entry.setdefault("run_id", self.recorder.dir.name)
        self.recorder.record(entry)

    def seal(self) -> None:
        self._sealed = True

    def ok_reason(self) -> str | None:
        if self.recorder.count == 0:
            return "无 HTTP 证据记录（reports/evidence 为空）"
        if not self._sealed:
            return "替身声明未封存（显式调用 scenario_evidence.seal() 声明外部依赖模式）"
        return None


@pytest.fixture
def scenario_evidence(request):
    sid = _state(request.config).sc_marker_id(request.node)
    if sid is None:
        yield None
        return
    st = _state(request.config)
    ev_dir = os.environ.get(isolation.ENV_EVIDENCE_DIR) or str(ROOT / "reports" / "evidence")
    recorder = EvidenceRecorder(pathlib.Path(ev_dir), f"{st.run_id}/{sid}")
    sm = ScenarioSettlement(sid, recorder)
    st.settlements[sid] = sm
    yield sm
