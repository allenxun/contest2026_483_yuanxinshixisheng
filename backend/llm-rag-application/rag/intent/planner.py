from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

from rag.intent.models import (
    IntentActionDefinition,
    IntentDefinition,
    IntentRecognitionResult,
    TargetType,
)


@dataclass(frozen=True)
class ExecutionAction:
    action_id: str
    action_type: TargetType
    intent_id: str
    target_name: str = ""
    query: str = ""
    information_need: str = ""
    arguments: Mapping[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()

# 执行计划（状态 + 动作列表 + 响应文本）
@dataclass(frozen=True)
class ExecutionPlan:
    status: Literal["ready", "clarify", "oos"]
    user_goal: str
    actions: tuple[ExecutionAction, ...] = ()
    response_text: str = ""
    reason_summary: str = ""

    @property
    def grounded(self) -> bool:
        return any(action.action_type in {"knowledge", "tool"} for action in self.actions)

# 将识别结果展开为动作列表，做权限校验和依赖排序
class IntentPlanBuilder:
    """Expand confirmed intents into an allow-listed, deterministic action plan."""

    def __init__(self, definitions: Sequence[IntentDefinition]):
        self.definition_by_id = {item.intent_id: item for item in definitions}

    def build(
        self,
        result: IntentRecognitionResult,
        *,
        allowed_knowledge_bases: Sequence[str],
        allowed_tools: Sequence[str],
    ) -> ExecutionPlan:
        goal = result.frame.normalized_user_goal
        kind = result.clarification_kind
        if result.status == "needs_clarification" and kind == "intent_disambiguation":
            question = result.clarification.question if result.clarification else "请补充您的具体需求。"
            return ExecutionPlan("clarify", goal, response_text=question, reason_summary=result.reason_summary)
        clarification_text = ""
        if result.status == "needs_clarification" and kind == "missing_input":
            clarification_text = (
                result.clarification.question
                if result.clarification else "请补充您的具体需求。"
            )
        if result.status == "oos":
            message = result.oos_summary or "当前系统暂时无法处理该需求。"
            return ExecutionPlan("oos", goal, response_text=message, reason_summary=result.reason_summary)
        if not result.can_route and not (
            result.status == "needs_clarification" and kind == "missing_input"
        ):
            return ExecutionPlan("clarify", goal, response_text="请补充您的具体需求。")

        allowed_kbs = tuple(dict.fromkeys(allowed_knowledge_bases))
        allowed_tool_set = set(allowed_tools)
        actions: list[ExecutionAction] = []
        for hypothesis in result.frame.hypotheses:
            definition = self.definition_by_id.get(hypothesis.intent_id)
            if definition is None:
                continue
            if (
                kind == "missing_input"
                and definition.target_type == "knowledge"
                and not result.frame.retrieval_queries
            ):
                continue
            if any(
                slot not in result.frame.confirmed_slots
                for slot in definition.required_slots
            ):
                continue
            configured = definition.actions or ()
            if not configured:
                configured = (IntentActionDefinition("route", definition.target_type, definition.target_name),)
            prefix = hypothesis.intent_id
            query_by_action = {
                item.action_id: (
                    result.frame.retrieval_queries
                    if item.action_type == "knowledge" and result.frame.retrieval_queries
                    else (result.frame.standalone_query or goal,)
                )
                for item in configured
            }
            local_ids = {
                item.action_id: tuple(
                    f"{prefix}:{item.action_id}:{index}"
                    if len(query_by_action[item.action_id]) > 1
                    else f"{prefix}:{item.action_id}"
                    for index, _ in enumerate(query_by_action[item.action_id], start=1)
                )
                for item in configured
            }
            for item in configured:
                target_name = item.target_name
                if item.action_type == "knowledge":
                    if target_name and target_name not in allowed_kbs:
                        continue
                    if not target_name:
                        target_name = allowed_kbs[0] if allowed_kbs else ""
                    if not target_name:
                        continue
                if item.action_type == "tool" and target_name not in allowed_tool_set:
                    continue
                queries = query_by_action[item.action_id]
                for query_index, query in enumerate(queries, start=1):
                    action_id = local_ids[item.action_id][query_index - 1]
                    need = ""
                    if query_index <= len(result.frame.information_needs):
                        need = result.frame.information_needs[query_index - 1]
                    actions.append(ExecutionAction(
                        action_id=action_id,
                        action_type=item.action_type,
                        intent_id=definition.intent_id,
                        target_name=target_name,
                        query=query,
                        information_need=need,
                        arguments=dict(result.frame.confirmed_slots),
                        depends_on=tuple(
                            dependency_id
                            for value in item.depends_on
                            for dependency_id in local_ids[value]
                        ),
                    ))

        if not actions and clarification_text:
            return ExecutionPlan(
                "clarify",
                goal,
                response_text=clarification_text,
                reason_summary=result.reason_summary,
            )
        if not actions:
            return ExecutionPlan(
                "oos",
                goal,
                response_text="当前身份没有可执行的知识库或工具能力。",
                reason_summary="已识别意图，但目标能力未授权或未配置",
            )
        self._validate_order(actions)
        return ExecutionPlan(
            "ready",
            goal,
            tuple(actions),
            response_text=clarification_text,
            reason_summary=result.reason_summary,
        )

    @staticmethod
    def _validate_order(actions: Sequence[ExecutionAction]) -> None:
        seen: set[str] = set()
        for action in actions:
            missing = set(action.depends_on).difference(seen)
            if missing:
                raise ValueError(f"action dependencies must precede action {action.action_id}: {sorted(missing)}")
            seen.add(action.action_id)
