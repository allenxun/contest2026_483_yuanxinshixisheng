from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegionCode(str, Enum):
    F = "F"
    C = "C"
    L = "L"
    R = "R"


class ConcernCode(str, Enum):
    O = "O"
    P = "P"
    D = "D"


class Severity(str, Enum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"


class ScoreReading(StrictModel):
    score: int | None = Field(default=None, ge=0, le=100)
    reported_label: str | None = None
    severity: Severity | None = None
    level_label: str | None = None
    issue: Literal["missing", "invalid", "conflict"] | None = None


class RegionReading(StrictModel):
    scores: dict[ConcernCode, ScoreReading]


class WeijingReport(StrictModel):
    report_id: str
    assessed_at: datetime
    algorithm_version: str
    filename: str
    file_sha256: str
    regions: dict[RegionCode, RegionReading]
    excluded_regions: list[str] = Field(default_factory=list)
    parsing_notes: list[str] = Field(default_factory=list)


class IngredientSelection(StrictModel):
    ingredient_id: str
    head_id: str
    name: str
    role: Literal["core", "support", "auxiliary"]
    regions: list[RegionCode]
    concerns: list[ConcernCode]
    reason: str
    study_frequency: str | None = None


class ExcludedCandidate(StrictModel):
    ingredient_id: str
    reason: str


class RegionGoal(StrictModel):
    region: RegionCode
    scores: dict[ConcernCode, ScoreReading]
    priority: list[ConcernCode]
    pattern_id: str | None = None
    ingredient_ids: list[str] = Field(default_factory=list)


class DailyIngredientTask(StrictModel):
    ingredient_id: str
    head_id: str
    regions: list[RegionCode]


class DailyTask(StrictModel):
    day: int = Field(ge=1, le=15)
    ingredients: list[DailyIngredientTask]
    review: bool = False
    device_enabled: bool = False
    actual_device_seconds: int = 0


class SafetyProfile(StrictModel):
    urgent_systemic: bool | None = None
    local_damage_or_pain: bool | None = None
    irritation: bool | None = None
    recent_procedure: bool | None = None
    diagnosed_disease_or_medication: bool | None = None
    adult_general: bool | None = None
    changing_bleeding_pigment: bool | None = None
    intolerances: list[str] = Field(default_factory=list)
    tolerated: list[str] = Field(default_factory=list)
    professional_review: Literal["pending", "passed", "failed", "na"] = "pending"
    device_status: Literal["MISSING", "SIMULATION", "VALIDATED"] = "MISSING"
    allocation_rules_confirmed: bool = False
    min_device_interval_hours: int | None = None
    last_device_hours_ago: int | None = None


class SafetyDecision(StrictModel):
    grade: Literal["G0", "G1", "G2", "G3", "unknown"]
    device_gate: Literal["candidate", "hold", "block"]
    referral_advice: Literal["none", "routine", "prompt", "urgent"]
    incomplete: bool
    reasons: list[str] = Field(default_factory=list)


class IngredientDemand(StrictModel):
    ingredient_id: str
    head_id: str = ""
    regions: list[RegionCode]
    role: Literal["core", "support", "auxiliary", "support_alternative"] = "core"
    required_dates: dict[str, list[int]] = Field(default_factory=dict)
    minimum_days: dict[str, int] = Field(default_factory=dict)
    alternative_group: str | None = None
    incompatible_dates: list[int] = Field(default_factory=list)


class DeviceAssignment(StrictModel):
    region: RegionCode
    head_id: str
    seconds: int = Field(ge=0)


class WeijingPlan(StrictModel):
    plan_id: str
    assessment_id: str
    knowledge_version: str = "1.0"
    status: Literal[
        "READY_CARE",
        "PREVIEW_ONLY",
        "REVIEW_REQUIRED",
        "PAUSED",
        "URGENT",
        "SCHEDULE_INFEASIBLE",
    ]
    assessment_integrity: Literal["complete", "partial", "conflict", "invalid"]
    selected_ingredients: list[IngredientSelection]
    excluded_candidates: list[ExcludedCandidate] = Field(default_factory=list)
    region_goals: list[RegionGoal]
    cycle_days: Literal[7, 10, 15] | None
    daily_tasks: list[DailyTask]
    care_application: Literal["ordinary_topical", "validated_device", "no_application"]
    device_enabled: bool
    actual_device_seconds: int = 0
    preview_device: dict | None = None
    exposure_summary: dict[str, dict[str, int]]
    scheduling_constraints: list[str]
    review_schedule: list[str]
    referral: str | None = None
    evidence_refs: list[str]
    project_rule_ids: list[str]
    safety_confirmation_required: bool = True
    device_gate: Literal["candidate", "hold", "block"] = "hold"
    conflicts: list[str] = Field(default_factory=list)


class WeijingAssessment(StrictModel):
    assessment_id: str
    user_id: str
    organization_id: str | None = None
    revision: int = 1
    report: WeijingReport
    plan: WeijingPlan
    rendered_markdown: str
    created_at: datetime
