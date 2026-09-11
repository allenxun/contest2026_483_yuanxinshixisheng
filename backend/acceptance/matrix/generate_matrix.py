#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从设计文档机械提取验收矩阵（唯一数据源，不手工转录）。

输入（只读）：
  backend/doc/测试场景清单-V1-五模块与双控制.md   —— 94 场景表
  backend/doc/后端API接口设计-V1-五模块与流程对应.md —— 27 API 定义

输出：
  matrix/scenarios.json  —— 场景追踪矩阵（JSON 数组，94 条）
  matrix/apis.json       —— API 反向索引（JSON 数组，27 条）

再生成：python3 matrix/generate_matrix.py（在 backend/acceptance 下运行）。
tests/test_matrix_integrity.py 会用独立解析器复核本脚本的输出，二者不一致即失败。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]        # backend/acceptance
DOC_DIR = ROOT.parent / "doc"                              # backend/doc
SCENARIO_DOC = DOC_DIR / "测试场景清单-V1-五模块与双控制.md"
API_DOC = DOC_DIR / "后端API接口设计-V1-五模块与流程对应.md"

# API → 负责工作包（总协调 2026-09-10 权威澄清；此前 M3→C/M4→D 为负责人归属错误）：
#   B = identity/devices/notifications：M1、M2、M5
#   D = assessments：M3（测肤 Java + 测肤/归档 Worker）、M4-A01/M4-A02（方案生成 Worker 相关）
#   C = care：M4-A03..M4-A09（执行/记账 HTTP）
# 场景 owner_package = 其关联 API 归属的并集（升序，跨包场景可为 B/C/D 组合）。
def api_owner(api_id: str) -> str:
    if api_id in ("M4-A01", "M4-A02"):
        return "D"
    return {"M1": "B", "M2": "B", "M3": "D", "M4": "C", "M5": "B"}[api_id[:2]]

# 验证范围 → 自动化分层
SCOPE_TO_TIER = {
    "后端": "现在可自动",
    "集成": "需替身",
    "联调": "需真实设备或APP",
}

TIER_EXTRA_REASON = {
    "需替身": "；本场景为集成范围，业务实现集成后须经 A 适配端口接入 face/LLM/push/OSS 测试替身",
    "需真实设备或APP": "；本场景为联调范围，还需真实云台/微晶/APP 参与，模拟通过不能替代",
    "现在可自动": "；本场景为后端 HTTP 范围，业务实现集成后可直接黑盒自动执行",
}

# 集成状态（2026-09-11）：C 最终代码 8b3592e 已集成（93b7e33）；B/D 未集成。
INTEGRATED_PACKAGES = {"C"}
C_ONLY_PENDING_REASON = (
    "C 已交付集成（8b3592e@93b7e33）；场景级 E2E 前置（成员/授权/设备/报告/方案生成）"
    "仍需 B/D 真实端点，C 断面已经 E-C 验收以测试种子验证（见 backend/handoffs/E-C-acceptance.md）"
)

# A 基线已于 2026-09-10 到达（E 独立基础验收见 evidence/A-baseline-*）。
# 场景的真实阻塞已变为 B/C/D 业务实现未集成：26 个业务端点为 501 NOT_IMPLEMENTED stub。
BASE_PENDING_REASON = (
    "A 基线已交付（候选 26d97fb，E 独立基础验收证据见 backend/acceptance/evidence/）；"
    "B/C/D 业务实现尚未集成：关联业务端点当前为 501 NOT_IMPLEMENTED stub，端到端不可执行"
)


def parse_apis() -> dict[str, dict]:
    """解析 27 个 API：id → {module, module_title, title, http}。"""
    text = API_DOC.read_text(encoding="utf-8")
    apis: dict[str, dict] = {}
    current: str | None = None
    module_titles: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^### (M\d) (\S.*?)\s*$", line)
        if m and "-" not in m.group(2):
            module_titles[m.group(1)] = m.group(2).strip()
            continue
        m = re.match(r"^#### (M\d-A\d{2}) · (.+?)\s*$", line)
        if m:
            current = m.group(1)
            apis[current] = {
                "id": current,
                "module": m.group(1)[:2],
                "module_title": module_titles.get(m.group(1)[:2], ""),
                "title": m.group(2).strip(),
                "http": "",
            }
            continue
        if current:
            m = re.search(r"\*\*接口\*\*：`(GET|POST|PUT|DELETE) (/[^`]*)`", line)
            if m:
                apis[current]["http"] = f"{m.group(1)} {m.group(2)}"
                current = None
    if len(apis) != 27:
        sys.exit(f"API 解析数量异常：{len(apis)} != 27")
    if any(not a["http"] or not a["title"] or not a["module_title"] for a in apis.values()):
        bad = [k for k, v in apis.items() if not v["http"] or not v["title"] or not v["module_title"]]
        sys.exit(f"API 字段解析不完整：{bad}")
    return apis


def parse_scenarios(all_api_ids: list[str]) -> list[dict]:
    """逐行解析场景表：| 编号 | 优先级 | 验证范围 | 场景 | 检查要点 | 关联API | 依赖 |"""
    text = SCENARIO_DOC.read_text(encoding="utf-8")
    section_titles: dict[str, str] = {}
    scenarios: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"^### (0\d|C|R) · (.+?)\s*$", line)
        if m:
            section_titles[f"SC-{m.group(1)}"] = f"SC-{m.group(1)} · {m.group(2).strip()}"
            continue
        if not re.match(r"^\|\s*SC-", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            sys.exit(f"场景行字段数异常（{len(cells)}）：{line[:60]}...")
        sid, priority, scope, title, checkpoints, api_cell, dep_cell = cells
        section_key = re.match(r"(SC-0[0-7]|SC-[CR])-\d{2}$", sid)
        if not section_key:
            sys.exit(f"场景编号异常：{sid}")
        if sid in seen:
            sys.exit(f"场景编号重复：{sid}")
        seen.add(sid)
        if api_cell == "全部 27 个 API":
            apis = list(all_api_ids)  # SC-C-01：文档原文即覆盖全部 27 个 API
        else:
            apis = re.findall(r"M\d-A\d{2}", api_cell)
            found = re.findall(r"[^\s、]+", api_cell)
            if len(apis) != len(found):
                sys.exit(f"场景 {sid} 关联 API 解析不完整：{api_cell}")
        deps = re.findall(r"D\d{2}", dep_cell)  # "—" → []
        if priority not in ("P0", "P1"):
            sys.exit(f"场景 {sid} 优先级异常：{priority}")
        if scope not in SCOPE_TO_TIER:
            sys.exit(f"场景 {sid} 验证范围异常：{scope}")
        packages = sorted({api_owner(a) for a in apis})
        tier = SCOPE_TO_TIER[scope]
        blocked = sorted(set(packages) - INTEGRATED_PACKAGES)
        if packages and not blocked:  # C-only：C 已集成
            reason = C_ONLY_PENDING_REASON + TIER_EXTRA_REASON[tier]
        else:
            reason = BASE_PENDING_REASON + TIER_EXTRA_REASON[tier]
        if deps:
            reason += "；涉及开发对接项：" + "、".join(deps)
        scenarios.append({
            "id": sid,
            "section": section_titles.get(section_key.group(1), section_key.group(1)),
            "priority": priority,
            "scope": scope,
            "title": title,
            "checkpoints": checkpoints,
            "apis": apis,
            "deps": deps,
            "owner_package": packages,
            "blocked_by": blocked,  # 真实阻塞=尚未集成包（C 已集成→移除）
            "automation_tier": tier,
            "status": "dependency_pending",
            "pending_reason": reason,
        })
    if len(scenarios) != 94:
        sys.exit(f"场景解析数量异常：{len(scenarios)} != 94")
    return scenarios


def main() -> None:
    apis = parse_apis()
    all_api_ids = sorted(apis)
    scenarios = parse_scenarios(all_api_ids)

    api_out = []
    for aid in all_api_ids:
        meta = apis[aid]
        related = [s["id"] for s in scenarios if aid in s["apis"]]
        api_out.append({
            "id": aid,
            "module": meta["module"],
            "module_title": meta["module_title"],
            "title": meta["title"],
            "http": meta["http"],
            "scenarios": related,
        })

    out_dir = ROOT / "matrix"
    (out_dir / "scenarios.json").write_text(
        json.dumps(scenarios, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "apis.json").write_text(
        json.dumps(api_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    p0 = sum(1 for s in scenarios if s["priority"] == "P0")
    p1 = sum(1 for s in scenarios if s["priority"] == "P1")
    print(f"OK scenarios={len(scenarios)} (P0={p0} P1={p1}) apis={len(api_out)}")


if __name__ == "__main__":
    main()
