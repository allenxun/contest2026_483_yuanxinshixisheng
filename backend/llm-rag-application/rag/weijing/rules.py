from __future__ import annotations

from rag.weijing.catalog import ingredient_record, knowledge_version, load_catalog
from rag.weijing.models import (
    ConcernCode,
    ExcludedCandidate,
    IngredientSelection,
    RegionCode,
    RegionGoal,
    SafetyDecision,
    SafetyProfile,
    ScoreReading,
    Severity,
    WeijingReport,
)


REGION_ORDER = (RegionCode.F, RegionCode.L, RegionCode.R, RegionCode.C)
CONCERN_TIE_ORDER = (ConcernCode.D, ConcernCode.P, ConcernCode.O)
LEVEL_LABELS = {
    Severity.S0: "未见明显",
    Severity.S1: "轻度",
    Severity.S2: "中度",
    Severity.S3: "较明显",
    Severity.S4: "显著",
}
ROLE_ORDER = {"core": 0, "support": 1, "auxiliary": 2}


def severity_for_score(score: int) -> Severity:
    if score >= 81:
        return Severity.S0
    if score >= 61:
        return Severity.S1
    if score >= 41:
        return Severity.S2
    if score >= 21:
        return Severity.S3
    return Severity.S4


def build_region_goals(report: WeijingReport) -> tuple[list[RegionGoal], str]:
    goals: list[RegionGoal] = []
    issues: list[str] = []
    for region in REGION_ORDER:
        if region not in report.regions:
            continue
        scored: dict[ConcernCode, ScoreReading] = {}
        for concern in ConcernCode:
            reading = report.regions[region].scores.get(concern, ScoreReading(issue="missing"))
            if reading.score is not None and reading.issue not in {"conflict", "invalid"}:
                severity = severity_for_score(reading.score)
                reading = reading.model_copy(update={
                    "severity": severity,
                    "level_label": LEVEL_LABELS[severity],
                })
            scored[concern] = reading
            if reading.issue:
                issues.append(reading.issue)
        active = [
            concern for concern, reading in scored.items()
            if reading.severity is not None and reading.severity != Severity.S0
        ]
        priority = sorted(
            active,
            key=lambda concern: (
                scored[concern].score if scored[concern].score is not None else 101,
                CONCERN_TIE_ORDER.index(concern),
            ),
        )
        pattern_id = None
        if active:
            patterns = load_catalog()["patterns"]
            pattern_id = next(
                (key for key, value in patterns.items() if set(value) == {item.value for item in active}),
                None,
            )
        goals.append(RegionGoal(
            region=region,
            scores=scored,
            priority=priority,
            pattern_id=pattern_id,
            ingredient_ids=[],
        ))
    if not goals:
        integrity = "invalid"
    elif "conflict" in issues:
        integrity = "conflict"
    elif issues or len(report.regions) < 4:
        integrity = "partial"
    else:
        integrity = "complete"
    return goals, integrity


def evaluate_safety(profile: SafetyProfile, goals: list[RegionGoal]) -> SafetyDecision:
    reasons: list[str] = []
    if profile.urgent_systemic is True:
        return SafetyDecision(
            grade="G3",
            device_gate="block",
            referral_advice="urgent",
            incomplete=False,
            reasons=["疑似全身严重过敏或紧急反应，停止全部美容任务"],
        )
    if profile.changing_bleeding_pigment is True or profile.local_damage_or_pain is True:
        grade = "G2"
        referral = "prompt"
        reasons.append("活动性病变、破损或变化性出血皮损，暂停相关设备并建议就医")
    elif profile.diagnosed_disease_or_medication is True:
        grade = "G2"
        referral = "prompt"
        reasons.append("活动期皮肤病或相关用药尚未协调")
    elif profile.irritation is True or profile.recent_procedure is True:
        grade = "G1"
        referral = "none"
        reasons.append("当下刺激、晒伤或近期操作，暂停设备并只保留简单护理")
    elif any(
        value is None for value in (
            profile.urgent_systemic,
            profile.local_damage_or_pain,
            profile.irritation,
            profile.recent_procedure,
            profile.diagnosed_disease_or_medication,
            profile.adult_general,
            profile.changing_bleeding_pigment,
        )
    ):
        grade = "unknown"
        referral = "none"
        reasons.append("安全问询不完整，不按无风险处理")
    else:
        grade = "G0"
        referral = "none"

    d_s4 = any(
        goal.scores[ConcernCode.D].severity == Severity.S4
        for goal in goals
        if ConcernCode.D in goal.scores
    )
    p_marked = any(
        goal.scores[concern].severity in {Severity.S3, Severity.S4}
        for goal in goals
        for concern in (ConcernCode.P,)
        if concern in goal.scores
    )
    if grade == "G0" and d_s4 and profile.professional_review != "passed":
        grade = "G1"
        reasons.append("D=S4 未专业复核，自动设备分支暂缓")
    if referral == "none" and p_marked and grade in {"G0", "unknown", "G1"}:
        referral = "routine"
        reasons.append("稳定色素负担较明显，常规推荐就医，不等于急性G2")

    device_gate = "candidate" if grade == "G0" else "hold"
    if grade in {"G2", "G3"}:
        device_gate = "block"
    if profile.device_status != "VALIDATED" or not profile.allocation_rules_confirmed:
        device_gate = "hold" if device_gate == "candidate" else device_gate
        reasons.append("设备参数不是已验证状态，实际设备时长为0")
    return SafetyDecision(
        grade=grade,
        device_gate=device_gate,
        referral_advice=referral,
        incomplete=grade == "unknown",
        reasons=reasons,
    )


def _selection(ingredient_id: str, role: str, regions: list[RegionCode], concerns: list[ConcernCode]) -> IngredientSelection:
    record = ingredient_record(ingredient_id)
    return IngredientSelection(
        ingredient_id=ingredient_id,
        head_id=record["head_id"],
        name=record["name"],
        role=role,
        regions=list(dict.fromkeys(regions)),
        concerns=list(dict.fromkeys(concerns)),
        reason=record["reason"],
        study_frequency=record.get("study_frequency"),
    )


def select_ingredients(
    goals: list[RegionGoal],
    *,
    safety: SafetyProfile | None = None,
    allow_auxiliary: bool = False,
) -> tuple[list[IngredientSelection], list[ExcludedCandidate]]:
    safety = safety or SafetyProfile()
    intolerances = {item.upper() for item in safety.intolerances}
    n_regions: list[RegionCode] = []
    h_regions: list[RegionCode] = []
    p_aux_regions: list[RegionCode] = []
    n_concerns: list[ConcernCode] = []
    for goal in goals:
        active = set(goal.priority)
        if not active:
            continue
        wants_n = bool(active & {ConcernCode.O, ConcernCode.P})
        wants_h = ConcernCode.D in active
        if wants_n:
            n_regions.append(goal.region)
            if ConcernCode.O in active:
                n_concerns.append(ConcernCode.O)
            if ConcernCode.P in active:
                n_concerns.append(ConcernCode.P)
        if wants_h:
            h_regions.append(goal.region)
        if ConcernCode.P in active and allow_auxiliary:
            p_aux_regions.append(goal.region)
        goal.ingredient_ids = []
        if wants_n and "IN01" not in intolerances:
            goal.ingredient_ids.append("IN01")
        if wants_h:
            goal.ingredient_ids.append("IN02")

    selected: list[IngredientSelection] = []
    excluded: list[ExcludedCandidate] = []
    if n_regions and "IN01" not in intolerances:
        selected.append(_selection("IN01", "core", n_regions, n_concerns or [ConcernCode.O]))
    elif n_regions:
        excluded.append(ExcludedCandidate(ingredient_id="IN01", reason="已知不耐受，不因其多作用而强制重试。"))
        if "IN11" not in intolerances and "IN11" in {item.upper() for item in safety.tolerated}:
            selected.append(_selection("IN11", "core", n_regions, [ConcernCode.O]))
        else:
            excluded.append(ExcludedCandidate(ingredient_id="IN11", reason="油脂备选证据较弱，且当前没有已耐受记录。"))
    if h_regions:
        selected.append(_selection(
            "IN02",
            "support" if selected else "core",
            h_regions,
            [ConcernCode.D],
        ))
    if allow_auxiliary and p_aux_regions and "IN07" not in intolerances:
        if "IN01" in {item.ingredient_id for item in selected}:
            selected.append(_selection("IN07", "auxiliary", p_aux_regions, [ConcernCode.P]))
        else:
            selected.append(_selection("IN07", "core", p_aux_regions, [ConcernCode.P]))

    selected = limit_untried_formulas(selected, tolerated=safety.tolerated)
    used = {item.ingredient_id for item in selected}
    for ingredient_id, record in load_catalog()["ingredients"].items():
        if ingredient_id in used:
            continue
        if ingredient_id == "IN01" and any(item.ingredient_id == "IN01" for item in excluded):
            continue
        excluded.append(ExcludedCandidate(
            ingredient_id=ingredient_id,
            reason=f"当前报告不需要将该{record['name']}纳入本周期；{record['reason']}",
        ))
    return selected, excluded


def limit_untried_formulas(
    selected: list[IngredientSelection],
    *,
    tolerated: list[str],
    max_new: int = 1,
) -> list[IngredientSelection]:
    tolerated_ids = {item.upper() for item in tolerated}
    kept: list[IngredientSelection] = []
    new_count = 0
    for item in sorted(selected, key=lambda value: ROLE_ORDER[value.role]):
        if item.ingredient_id.upper() in tolerated_ids:
            kept.append(item)
            continue
        if new_count < max_new:
            kept.append(item)
            new_count += 1
    if not tolerated_ids and len(selected) <= 2 and all(item.role in {"core", "support"} for item in selected):
        return selected
    return kept or selected[:1]


def choose_cycle_days(
    goals: list[RegionGoal],
    selected: list[IngredientSelection],
    *,
    tolerated: list[str],
) -> int | None:
    if not selected:
        return None
    tolerated_ids = {item.upper() for item in tolerated}
    has_aux = any(item.role == "auxiliary" for item in selected)
    active_regions = [goal for goal in goals if goal.priority]
    all_tolerated = bool(selected) and all(item.ingredient_id.upper() in tolerated_ids for item in selected)
    if has_aux and all_tolerated:
        return 10
    if len(active_regions) >= 3 and all_tolerated:
        return 15
    return 7


def has_d_s4_unreviewed(goals: list[RegionGoal], profile: SafetyProfile) -> bool:
    return profile.professional_review != "passed" and any(
        goal.scores.get(ConcernCode.D) and goal.scores[ConcernCode.D].severity == Severity.S4
        for goal in goals
    )


def decide_plan_status(
    safety: SafetyDecision,
    *,
    d_s4_unreviewed: bool,
    schedule_conflicts: list[str],
) -> str:
    if safety.grade == "G3":
        return "URGENT"
    if schedule_conflicts:
        return "SCHEDULE_INFEASIBLE"
    if safety.grade == "G2":
        return "PAUSED"
    if d_s4_unreviewed:
        return "REVIEW_REQUIRED"
    if safety.incomplete:
        return "PREVIEW_ONLY"
    return "READY_CARE"


def referral_text(decision: SafetyDecision) -> str | None:
    mapping = {
        "urgent": "出现呼吸困难、口唇舌咽肿胀或迅速加重的全身反应时，停止使用并立即寻求急救。",
        "prompt": "请尽快就医评估活动性病变或未协调的医疗安排，不自行停用处方药，也不继续相关设备。",
        "routine": "若色素问题持续或明显，推荐就医明确斑型后再评估药物或光电项目；图像评分本身不是诊断。",
    }
    return mapping.get(decision.referral_advice)


def knowledge_meta() -> tuple[str, list[str], list[str]]:
    catalog = load_catalog()
    evidence = []
    for record in catalog["ingredients"].values():
        evidence.extend(record.get("evidence_refs") or [])
    return (
        knowledge_version(),
        list(dict.fromkeys(evidence)),
        list(catalog.get("project_rule_ids") or []),
    )
