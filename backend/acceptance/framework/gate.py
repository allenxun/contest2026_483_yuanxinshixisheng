# -*- coding: utf-8 -*-
"""基线门控与场景测试工厂。

语义（诚实报告的核心）：
- gate=closed（B/C/D 业务实现未集成；A 基线已交付）：所有场景测试以 skip 抛出，但 reason 固定前缀
  ``dependency_pending: ``，由 framework/conftest.py 插件统计为 dependency_pending，
  matrix 模式最终退出码为 3 —— 绝不冒充 0/通过。
- gate=open（A 基线交付并由协调者更新 config/baseline.json 后）：场景步骤若尚未
  编写则 fail("scenario steps not yet authored")，绝不静默 skip。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]  # backend/acceptance
BASELINE_PATH = ROOT / "config" / "baseline.json"
SCENARIOS_PATH = ROOT / "matrix" / "scenarios.json"

PENDING_PREFIX = "dependency_pending: "
VALID_GATES = ("closed", "open")


def load_baseline(path: pathlib.Path | None = None) -> dict:
    """读取并校验基线门控文件。缺失或非法即抛错，不允许默认放行。"""
    data = json.loads((path or BASELINE_PATH).read_text(encoding="utf-8"))
    if data.get("gate") not in VALID_GATES:
        raise ValueError(f"baseline.json gate 非法：{data.get('gate')!r}，应为 {VALID_GATES}")
    if not isinstance(data.get("a_baseline"), dict) or "sha" not in data["a_baseline"]:
        raise ValueError("baseline.json 缺少 a_baseline.sha 字段")
    if data["gate"] == "open" and not data["a_baseline"]["sha"]:
        raise ValueError("gate=open 但 a_baseline.sha 为空：门控配置不一致（fail-closed 拒绝）")
    return data


def current_gate(path: pathlib.Path | None = None) -> str:
    return load_baseline(path)["gate"]


_scenarios_cache: dict[str, dict] | None = None


def load_scenarios() -> dict[str, dict]:
    """加载场景矩阵 id → 元数据。"""
    global _scenarios_cache
    if _scenarios_cache is None:
        items = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
        _scenarios_cache = {s["id"]: s for s in items}
    return _scenarios_cache


def run_scenario_gate(scenario_id: str) -> None:
    """所有场景测试统一入口：按基线门控给出 skip/fail，永不静默通过。"""
    meta = load_scenarios()[scenario_id]
    if current_gate() == "closed":
        pytest.skip(PENDING_PREFIX + meta["pending_reason"], allow_module_level=False)
    # gate 已打开：A 基线交付后须为每个场景补写具体步骤（见 plans/ 与 README）。
    pytest.fail("scenario steps not yet authored", pytrace=False)


def _safe_name(scenario_id: str) -> str:
    return "test_" + re.sub(r"[^0-9A-Za-z]+", "_", scenario_id)


def make_scenario_tests(section: str) -> dict:
    """为一个清单小节生成全部 pytest 测试函数（名称含场景 ID，带全套 markers）。

    markers: sc_id / priority / scope / package(可重复) / deps(可重复)。
    """
    out: dict[str, object] = {}
    for sid, meta in load_scenarios().items():
        if not sid.startswith(f"{section}-"):
            continue

        def _gate(_sid: str = sid) -> None:
            run_scenario_gate(_sid)

        fn = _gate
        fn.__name__ = fn.__qualname__ = _safe_name(sid)
        fn.__doc__ = f"[{sid}][{meta['priority']}][{meta['scope']}] {meta['title']}"
        fn = pytest.mark.sc_id(sid)(fn)
        fn = pytest.mark.priority(meta["priority"])(fn)
        fn = pytest.mark.scope(meta["scope"])(fn)
        for pkg in meta["owner_package"]:
            fn = pytest.mark.package(pkg)(fn)
        for dep in meta["deps"]:
            fn = pytest.mark.deps(dep)(fn)
        out[fn.__name__] = fn
    return out
