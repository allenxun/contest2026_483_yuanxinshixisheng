# -*- coding: utf-8 -*-
"""E 验收 pytest 插件：marker 注册、dependency_pending 统计、matrix 退出码。

由 backend/acceptance/conftest.py 经 pytest_plugins 加载（顶层 conftest 合法）。

规则：
- 场景测试在 gate=closed 时 skip，reason 前缀固定 ``dependency_pending: ``；
  本插件把这类 skip 与普通 skipped 分开统计，并在终端摘要输出
  ``PASSED=n DEPENDENCY_PENDING=m FAILED=k``。
- 模式来自环境变量 E_ACCEPTANCE_MODE（run.sh 注入）：
    selfcheck → 只跑框架自检，退出码保持 pytest 原生 0/1；
    matrix    → 若存在 dependency_pending 且无失败，最终退出码强制为 3（绝不 0）；
                若有失败则维持 1。未注入模式时按 matrix 处理（fail-safe，
                宁可 3 也不给假 0）。
"""
from __future__ import annotations

import os

import pytest

from framework.gate import PENDING_PREFIX

MARKERS = (
    ("sc_id", "场景编号标记，如 sc_id('SC-00-01')"),
    ("priority", "清单优先级 P0/P1"),
    ("scope", "验证范围：后端/集成/联调"),
    ("package", "负责业务工作包：B/C/D（可重复标记）"),
    ("deps", "开发对接项 D01-D08（可重复标记）"),
)


def pytest_configure(config: pytest.Config) -> None:
    for name, desc in MARKERS:
        config.addinivalue_line("markers", f"{name}(value): {desc}")
    config._e_acc = {"passed": 0, "failed": 0, "pending": 0, "skipped_other": 0}


def _counts(config: pytest.Config) -> dict[str, int]:
    return getattr(config, "_e_acc", {"passed": 0, "failed": 0, "pending": 0, "skipped_other": 0})


def _mode() -> str:
    return os.environ.get("E_ACCEPTANCE_MODE", "matrix")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    rep = outcome.get_result()
    counts = getattr(item.session.config, "_e_acc", None)
    if counts is None:  # pragma: no cover - defensive
        return
    if rep.when == "call" and rep.passed:
        counts["passed"] += 1
    elif rep.skipped and PENDING_PREFIX in str(rep.longrepr or ""):
        counts["pending"] += 1  # dependency_pending 单独统计，不算普通 skipped
    elif rep.failed:
        counts["failed"] += 1
    elif rep.skipped:
        counts["skipped_other"] += 1


def pytest_terminal_summary(terminalreporter: "pytest.TerminalReporter",
                            exitstatus: int, config: pytest.Config) -> None:
    c = _counts(config)
    terminalreporter.write_sep("=", "E 验收统计")
    terminalreporter.write_line(
        f"PASSED={c['passed']} DEPENDENCY_PENDING={c['pending']} FAILED={c['failed']} "
        f"SKIPPED_OTHER={c['skipped_other']} MODE={_mode()}")
    if c["pending"]:
        terminalreporter.write_line(
            "说明：dependency_pending = A 基线未交付导致的依赖挂起，不是通过，也不是普通跳过。")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _mode() != "selfcheck":
        c = _counts(session.config)
        if c["failed"] > 0:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED  # 维持 1
        elif c["pending"] > 0:
            session.exitstatus = 3  # 有挂起场景：绝不返回 0
