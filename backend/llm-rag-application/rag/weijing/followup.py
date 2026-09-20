from __future__ import annotations

import json
import re

from rag.connector.database.repository.weijing_assessment_repository import (
    WeijingAssessmentNotFoundError,
    WeijingAssessmentRepository,
)
from rag.intent import ExecutionAction, ExecutionPlan
from rag.weijing.models import WeijingAssessment

ANONYMOUS_OWNER = "anonymous"
FOLLOWUP_ASSESSMENT_ID = "weijing_assessment_id"
FOLLOWUP_OWNER_ID = "weijing_owner_id"
_REPORT_FOLLOWUP = re.compile(
    r"(这个|这份|该|左脸|右脸|额部|下巴)?.{0,8}(分数|成分|方案|报告|排程|头位|精华)"
)


def resolve_owner_id(payload: dict) -> str:
    device_id = str((payload or {}).get("device_id") or "").strip()
    user_id = str((payload or {}).get("user_id") or "").strip()
    if device_id:
        return f"device:{device_id}"
    if user_id:
        return user_id
    return ANONYMOUS_OWNER


def followup_continuation_state(assessment: WeijingAssessment) -> dict[str, str]:
    return {
        FOLLOWUP_ASSESSMENT_ID: assessment.assessment_id,
        FOLLOWUP_OWNER_ID: assessment.user_id,
    }


def extract_followup_keys(state: dict | None) -> dict[str, str]:
    incoming = dict(state or {})
    keys = {}
    assessment_id = str(incoming.get(FOLLOWUP_ASSESSMENT_ID) or "").strip()
    owner_id = str(incoming.get(FOLLOWUP_OWNER_ID) or "").strip()
    if assessment_id:
        keys[FOLLOWUP_ASSESSMENT_ID] = assessment_id
    if owner_id:
        keys[FOLLOWUP_OWNER_ID] = owner_id
    return keys


def compact_weijing_assessment_context(assessment) -> str:
    plan = assessment.plan
    regions = {}
    for region, reading in assessment.report.regions.items():
        region_key = getattr(region, "value", region)
        regions[region_key] = {
            getattr(concern, "value", concern): {
                "score": item.score,
                "severity": getattr(item.severity, "value", item.severity),
                "issue": item.issue,
            }
            for concern, item in reading.scores.items()
        }
    payload = {
        "assessment_id": assessment.assessment_id,
        "report_id": assessment.report.report_id,
        "status": plan.status,
        "cycle_days": plan.cycle_days,
        "regions": regions,
        "selected_ingredients": [
            {
                "ingredient_id": item.ingredient_id,
                "name": item.name,
                "role": item.role,
                "regions": [getattr(region, "value", region) for region in item.regions],
            }
            for item in plan.selected_ingredients
        ],
        "device_enabled": plan.device_enabled,
        "actual_device_seconds": plan.actual_device_seconds,
    }
    return json.dumps(payload, ensure_ascii=False)


def load_assessment_context(
    state: dict | None,
    *,
    repository: WeijingAssessmentRepository | None = None,
) -> str:
    keys = extract_followup_keys(state)
    if not keys:
        return ""
    owner_id = keys.get(FOLLOWUP_OWNER_ID) or ANONYMOUS_OWNER
    assessment_id = keys.get(FOLLOWUP_ASSESSMENT_ID)
    store = repository or WeijingAssessmentRepository()
    try:
        if assessment_id:
            assessment = store.get(assessment_id, owner_id, None)
        else:
            assessment = store.latest_for_user(owner_id, None)
            if assessment is None:
                return ""
    except WeijingAssessmentNotFoundError:
        return ""
    return compact_weijing_assessment_context(assessment)


def assessment_followup_can_skip_clarification(query: str, assessment_context: str) -> bool:
    if not assessment_context:
        return False
    return bool(_REPORT_FOLLOWUP.search(query or ""))


def plan_with_assessment_followup(plan, query: str, assessment_context: str):
    if plan.status == "ready" or not assessment_followup_can_skip_clarification(query, assessment_context):
        return plan
    return ExecutionPlan(
        "ready",
        plan.user_goal or query,
        actions=(
            ExecutionAction(
                action_id="weijing:followup",
                action_type="knowledge",
                intent_id="weijing_followup",
                target_name="weijing_knowledge",
                query=query,
            ),
        ),
        reason_summary="使用当前检测报告上下文继续回答，不再追问同一份报告。",
    )
