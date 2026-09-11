# -*- coding: utf-8 -*-
"""SC 场景目录 conftest：gate=open 的 matrix 活体服务 session 夹具。

仅矩阵真实实测（E_ACCEPTANCE_MODE=matrix 且 baseline gate=open）时启动
PG/Java（dev，限堆 640m）；selfcheck 等模式不触发。证据落
evidence/Integration-<date>-<shortSHA>/<RUN_ID>/scenarios/<SC-ID>/。
"""
from __future__ import annotations

import os

import pytest

from framework import gate
from framework import live


@pytest.fixture(scope="session", autouse=True)
def _integration_live_services():
    if gate.current_gate() != "open" or os.environ.get("E_ACCEPTANCE_MODE") != "matrix":
        yield
        return
    os.environ.setdefault("E_ACCEPTANCE_EVIDENCE_DIR", str(live.evidence_base()))
    live.start_services()
    try:
        yield
    finally:
        live.stop_services()


@pytest.fixture(autouse=True)
def _scenario_gate_guard(request):
    """gate=closed（含 selfcheck 强制降级）时，所有场景节点 skip（dependency_pending）。

    手写的真实步骤节点绕过了 gate 工厂，故在此统一补齐门控；gate=open 时不干预。
    """
    if gate.current_gate() == "open":
        yield
        return
    mark = request.node.get_closest_marker("sc_id")
    sid = mark.args[0] if mark and mark.args else request.node.name
    pytest.skip(gate.PENDING_PREFIX + f"gate=closed（{sid}）", allow_module_level=False)

