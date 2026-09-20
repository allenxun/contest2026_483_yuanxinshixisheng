from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

from rag.weijing.catalog import knowledge_version
from rag.weijing.device import actual_device_seconds, interval_conflict, sim_region_budget
from rag.weijing.models import (
    SafetyProfile,
    Severity,
    WeijingAssessment,
    WeijingPlan,
    WeijingReport,
)
from rag.weijing.renderer import render_plan
from rag.weijing.report_input import report_from_payload
from rag.weijing.report_parser import parse_weijing_report
from rag.weijing.rules import (
    build_region_goals,
    choose_cycle_days,
    decide_plan_status,
    evaluate_safety,
    has_d_s4_unreviewed,
    knowledge_meta,
    referral_text,
    select_ingredients,
)
from rag.weijing.scheduler import ScheduleInfeasibleError, build_schedule


class AssessmentRepository(Protocol):
    def save(self, assessment: WeijingAssessment) -> WeijingAssessment: ...
    def get(self, assessment_id: str, user_id: str, organization_id: str | None) -> WeijingAssessment: ...
    def latest_for_user(self, user_id: str, organization_id: str | None) -> WeijingAssessment | None: ...


class WeijingAssessmentService:
    def __init__(self, repository: AssessmentRepository):
        self.repository = repository

    def assess(
        self,
        data: bytes,
        filename: str,
        *,
        user_id: str,
        organization_id: str | None,
        safety: SafetyProfile | None = None,
    ) -> WeijingAssessment:
        return self.assess_from_report(
            parse_weijing_report(data, filename),
            user_id=user_id,
            organization_id=organization_id,
            safety=safety,
        )

    def assess_from_payload(
        self,
        payload: dict,
        *,
        user_id: str,
        organization_id: str | None,
    ) -> WeijingAssessment:
        report, safety = report_from_payload(payload)
        return self.assess_from_report(
            report,
            user_id=user_id,
            organization_id=organization_id,
            safety=safety,
        )

    def assess_from_report(
        self,
        report: WeijingReport,
        *,
        user_id: str,
        organization_id: str | None,
        safety: SafetyProfile | None = None,
    ) -> WeijingAssessment:
        assessment_id = str(uuid.uuid4())
        profile = safety or SafetyProfile()
        goals, integrity = build_region_goals(report)
        decision = evaluate_safety(profile, goals)
        d_s4_unreviewed = has_d_s4_unreviewed(goals, profile)
        allow_auxiliary = bool(profile.tolerated) and decision.grade == "G0"
        if decision.grade == "G3":
            selected, excluded = [], []
            tasks, exposure, conflicts = [], {}, []
            cycle_days = None
        else:
            selected, excluded = select_ingredients(
                goals,
                safety=profile,
                allow_auxiliary=allow_auxiliary,
            )
            if decision.grade in {"G1", "G2"} and not decision.incomplete:
                tolerated = {item.upper() for item in profile.tolerated}
                selected = [
                    item for item in selected
                    if item.role == "support" or item.ingredient_id.upper() in tolerated
                ]
            cycle_days = choose_cycle_days(goals, selected, tolerated=profile.tolerated)
            tasks, exposure, conflicts = [], {}, []
            if selected and cycle_days:
                try:
                    tasks, exposure = build_schedule(selected, cycle_days=cycle_days)
                except ScheduleInfeasibleError as exc:
                    conflicts = list(exc.conflicts)
        if interval_conflict(profile.last_device_hours_ago, profile.min_device_interval_hours):
            conflicts.append("跨周期设备间隔不足，不清零历史，不补排密集任务")
        status = decide_plan_status(
            decision,
            d_s4_unreviewed=d_s4_unreviewed,
            schedule_conflicts=conflicts,
        )
        device_seconds = actual_device_seconds(profile.device_status, profile.allocation_rules_confirmed)
        preview = None
        if profile.device_status == "SIMULATION":
            preview = {
                "profile": "SIM-01",
                "for_human_use": False,
                "budgets": {
                    goal.region.value: sim_region_budget(
                        goal.region,
                        next((item.severity for item in goal.scores.values() if item.severity and item.severity != Severity.S0), Severity.S1),
                    )
                    for goal in goals
                    if goal.priority
                },
            }
        version, evidence_refs, rule_ids = knowledge_meta()
        constraints = [
            "每日全脸最多3种",
            "任一区每日最多2种",
            "同一成分跨区去重",
            "换头不重置累计量",
            *decision.reasons,
            *conflicts,
        ]
        for item in selected:
            if item.study_frequency:
                constraints.append(f"{item.name}：{item.study_frequency}；本模板按每日一次或间歇日安排，不复制原研究效果承诺。")
        care = "no_application" if status == "URGENT" else "ordinary_topical"
        plan = WeijingPlan(
            plan_id=str(uuid.uuid4()),
            assessment_id=assessment_id,
            knowledge_version=version or knowledge_version(),
            status=status,
            assessment_integrity=integrity,
            selected_ingredients=selected,
            excluded_candidates=excluded,
            region_goals=goals,
            cycle_days=cycle_days,
            daily_tasks=[] if status in {"URGENT", "SCHEDULE_INFEASIBLE"} else tasks,
            care_application=care,
            device_enabled=False,
            actual_device_seconds=device_seconds,
            preview_device=preview,
            exposure_summary=exposure,
            scheduling_constraints=constraints,
            review_schedule=_review_copy(cycle_days),
            referral=referral_text(decision),
            evidence_refs=evidence_refs,
            project_rule_ids=rule_ids,
            device_gate=decision.device_gate,
            conflicts=conflicts,
        )
        rendered = render_plan(report, plan)
        assessment = WeijingAssessment(
            assessment_id=assessment_id,
            user_id=user_id,
            organization_id=organization_id,
            report=report,
            plan=plan,
            rendered_markdown=rendered,
            created_at=datetime.now(timezone.utc),
        )
        return self.repository.save(assessment)

    def get(self, assessment_id: str, *, user_id: str, organization_id: str | None) -> WeijingAssessment:
        return self.repository.get(assessment_id, user_id, organization_id)

    def latest_for_user(self, *, user_id: str, organization_id: str | None) -> WeijingAssessment | None:
        return self.repository.latest_for_user(user_id, organization_id)


def _review_copy(cycle_days: int | None) -> list[str]:
    if not cycle_days:
        return ["出现不适时立即暂停并评估，不等待周期结束。"]
    items = [f"D{cycle_days}复盘耐受与执行情况", "出现不适时提前暂停并评估"]
    if cycle_days == 15:
        items.insert(0, "D8中期复盘，不凭小幅分差升级")
    return items
