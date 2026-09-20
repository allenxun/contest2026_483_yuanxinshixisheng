# -*- coding: utf-8 -*-
"""外部替身登记与证据分级（只定义结构与标签，不实现生产替身）。

原则（对应任务书与 E-acceptance.md）：
- 替身必须通过 A 提供的适配端口（face/LLM/push/OSS 等接口边界）注入被测系统，
  E 不自建任何生产实现，也不测内部函数。
- 场景执行前用 DoublesManifest 声明每个外部协作者的模式；证据标签按最保守口径：
  只要有一个关键外部依赖是 double，结论只能记 ``doubles_pass``；
  全部关键外部依赖为真实供应商/设备且观察到真实结果，才允许 ``real_pass``。
  模拟通过不得冒充真实设备停止、人脸连续性或手机实际收到通知。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

#: 本版外部协作方（来源：运行组件说明/API 设计；不含内部实现细节）
DOUBLE_KINDS = ("face_algo", "skin_algo", "llm_plan", "push_channel", "oss", "gimbal_device", "microcrystal")

#: 联调硬门槛：这些结论即使全 double 也必须另行真实验证，不能只记 doubles_pass
REAL_ONLY_CHECKPOINTS = ("设备实际停止", "人脸连续性", "手机实际收到通知", "真实算法准确率")


@dataclass(frozen=True)
class DependencyUsage:
    kind: str            # DOUBLE_KINDS 之一
    mode: str            # "double" | "real"
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in DOUBLE_KINDS:
            raise ValueError(f"未登记的外部依赖类型：{self.kind}，允许：{DOUBLE_KINDS}")
        if self.mode not in ("double", "real"):
            raise ValueError(f"mode 必须是 double/real：{self.mode}")


@dataclass
class DoublesManifest:
    """场景运行声明：本次执行依赖哪些外部方、各自真实或替身。"""
    scenario_id: str
    usages: list[DependencyUsage] = field(default_factory=list)

    def add(self, kind: str, mode: str, note: str = "") -> "DoublesManifest":
        self.usages.append(DependencyUsage(kind=kind, mode=mode, note=note))
        return self

    def modes(self) -> set[str]:
        return {u.mode for u in self.usages}

    def evidence_tag(self) -> str:
        """返回 doubles_pass / real_pass / mixed / no_externals。"""
        m = self.modes()
        if not m:
            return "no_externals"
        if m == {"real"}:
            return "real_pass"
        if m == {"double"}:
            return "doubles_pass"
        return "mixed"  # 部分真实：按最保守口径呈现，需逐项注明未真实部分

    def assert_claimable(self, claim: str) -> None:
        """守卫：阻止把 doubles 结果申报为真实通过。"""
        if claim == "real_pass" and self.evidence_tag() != "real_pass":
            raise AssertionError(
                f"{self.scenario_id}: 外部依赖含替身/缺真实证据，只能记 "
                f"{self.evidence_tag()}，不得申报 real_pass")


def summarize(manifests: Iterable[DoublesManifest]) -> dict[str, int]:
    """汇总一批场景声明的标签计数（用于报告区分替身通过与真实通过）。"""
    out: dict[str, int] = {}
    for mf in manifests:
        tag = mf.evidence_tag()
        out[tag] = out.get(tag, 0) + 1
    return out
