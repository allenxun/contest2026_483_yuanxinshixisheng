from __future__ import annotations

from rag.weijing.models import ConcernCode, DailyTask, IngredientSelection, RegionCode, WeijingPlan, WeijingReport


REGION_LABELS = {RegionCode.F: "额头", RegionCode.C: "下巴", RegionCode.L: "左脸", RegionCode.R: "右脸"}
CONCERN_LABELS = {ConcernCode.O: "出油", ConcernCode.P: "色斑", ConcernCode.D: "干燥细纹"}
CONCERN_ACTIONS = {ConcernCode.O: "控油", ConcernCode.P: "淡斑", ConcernCode.D: "补水"}
STATUS_NOTES = {
    "READY_CARE": None,
    "PREVIEW_ONLY": "这次先按日常精华护理，暂不使用仪器。",
    "REVIEW_REQUIRED": "有些情况需要专业人员看过后再继续。",
    "PAUSED": "相关护理先暂停。",
    "URGENT": "请先处理不适或及时就医，这次不安排护肤操作。",
    "SCHEDULE_INFEASIBLE": "这次没法排出合适日程，请稍后再试。",
}


def render_plan(report: WeijingReport, plan: WeijingPlan) -> str:
    names = {item.ingredient_id: _plain_name(item.name) for item in plan.selected_ingredients}
    lines = ["## 你的护理建议", ""]
    note = STATUS_NOTES.get(plan.status)
    if note:
        lines.extend([note, ""])

    if plan.status == "URGENT":
        lines.extend(_safety_lines(plan))
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(["### 皮肤现在怎么样", ""])
    overview = _skin_overview(plan)
    lines.extend(overview or ["- 这次没有需要特别加强的项目。"])
    if report.excluded_regions:
        lines.append("不含" + "、".join(report.excluded_regions) + "。")

    lines.extend(["", "### 这几天用什么", ""])
    if plan.selected_ingredients:
        lines.extend(_ingredient_line(item) for item in plan.selected_ingredients)
    else:
        lines.append("- 保持温和清洁、保湿和日常防晒即可。")

    if plan.status == "SCHEDULE_INFEASIBLE":
        lines.extend(["", "### 安排说明", ""])
        lines.append("- 这次没法排出合适日程，先不要自行加量或换仪器。")
    elif plan.daily_tasks:
        lines.extend(["", f"### {plan.cycle_days} 天怎么用", ""])
        lines.extend(_schedule_lines(plan.daily_tasks, names))

    lines.extend(["", "### 使用前请看", ""])
    lines.extend(_safety_lines(plan))
    return "\n".join(lines).rstrip() + "\n"


def _skin_overview(plan: WeijingPlan) -> list[str]:
    lines = []
    for goal in plan.region_goals:
        parts = []
        for concern in ConcernCode:
            reading = goal.scores[concern]
            if reading.issue in {"missing", "invalid"}:
                parts.append(f"{CONCERN_LABELS[concern]}这次没测清楚")
            elif reading.issue == "conflict":
                parts.append(f"{CONCERN_LABELS[concern]}结果有冲突，先不作为依据")
            elif reading.level_label and reading.level_label != "未见明显":
                parts.append(f"{CONCERN_LABELS[concern]}{reading.level_label}")
        if parts:
            lines.append(f"- **{REGION_LABELS[goal.region]}**：{'，'.join(parts)}")
    return lines


def _plain_name(name: str) -> str:
    parts = [part for part in name.replace("/", " ").split() if any("\u4e00" <= char <= "\u9fff" for char in part)]
    return parts[0] if parts else name


def _region_text(regions: list[RegionCode]) -> str:
    ordered = [REGION_LABELS[region] for region in (RegionCode.F, RegionCode.L, RegionCode.R, RegionCode.C) if region in regions]
    if len(ordered) == 4:
        return "全脸"
    return "、".join(ordered)


def _ingredient_line(item: IngredientSelection) -> str:
    actions = "、".join(dict.fromkeys(CONCERN_ACTIONS[concern] for concern in item.concerns))
    return f"- **{_plain_name(item.name)}**：用在{_region_text(item.regions)}，主要帮你{actions}。"


def _schedule_lines(tasks: list[DailyTask], names: dict[str, str]) -> list[str]:
    groups: list[tuple[int, int, DailyTask]] = []
    for task in tasks:
        if groups and _task_signature(groups[-1][2]) == _task_signature(task):
            start, _, sample = groups[-1]
            groups[-1] = (start, task.day, sample)
        else:
            groups.append((task.day, task.day, task))

    last_day = tasks[-1].day
    lines = []
    for start, end, task in groups:
        content = _task_content(task, names)
        if start == 1 and end == last_day:
            prefix = "每天"
        elif start == end:
            prefix = f"第{start}天"
        else:
            prefix = f"第{start}–{end}天"
        lines.append(f"- {prefix}：{content}")
    lines.append("- 最后一天看看皮肤舒不舒服，有刺痛、发红就先停。")
    return lines


def _task_signature(task: DailyTask) -> tuple:
    return tuple((item.ingredient_id, tuple(item.regions)) for item in task.ingredients)


def _task_content(task: DailyTask, names: dict[str, str]) -> str:
    if not task.ingredients:
        return "维持基础护理，不新增加强精华。"
    parts = []
    for item in task.ingredients:
        name = names.get(item.ingredient_id, "精华")
        parts.append(f"{name}用在{_region_text(item.regions)}")
    return "；".join(parts) + "。用日常精华即可。"


def _safety_lines(plan: WeijingPlan) -> list[str]:
    lines = [
        "- 皮肤破了、红肿热痛、过敏刺痛，或刚晒伤、刚做完医美时，相关部位先别用。",
        "- 用的过程中不舒服就马上停。",
        "- 这是护肤建议，不是看病诊断，也不保证分数一定变好。不要为了护肤自己停药。",
    ]
    referral = _plain_referral(plan.referral)
    if referral:
        lines.append(f"- {referral}")
    return lines


def _plain_referral(text: str | None) -> str | None:
    if not text:
        return None
    if "急救" in text:
        return "如果呼吸困难、嘴脸迅速肿胀，请立刻停用并急救。"
    if "尽快就医" in text:
        return "请尽快就医，不要自己停药，也不要继续用仪器。"
    if "色素" in text or "斑" in text:
        return "色斑如果一直比较明显，建议去医院看一下是什么类型，再决定下一步。测肤分数不能代替医生诊断。"
    return text
