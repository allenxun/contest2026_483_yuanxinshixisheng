from __future__ import annotations

from rag.weijing.models import (
    DailyIngredientTask,
    DailyTask,
    IngredientDemand,
    IngredientSelection,
    RegionCode,
)


REGION_ORDER = (RegionCode.F, RegionCode.L, RegionCode.R, RegionCode.C)
FACE_DAILY_LIMIT = 3
REGION_DAILY_LIMIT = 2
TEN_DAY_B = {3, 7}
FIFTEEN_DAY_B = {3, 7, 10, 13}
REVIEW_DAYS = {7: {7}, 10: {10}, 15: {8, 15}}


class ScheduleInfeasibleError(ValueError):
    def __init__(self, conflicts: list[str]):
        super().__init__("；".join(conflicts))
        self.conflicts = conflicts


def build_schedule(
    ingredients: list[IngredientSelection],
    *,
    cycle_days: int = 7,
) -> tuple[list[DailyTask], dict[str, dict[str, int]]]:
    if cycle_days not in {7, 10, 15}:
        raise ValueError("cycle_days must be 7, 10, or 15")
    if len(ingredients) > 3:
        raise ScheduleInfeasibleError(["全脸当日不能安排第4个成分，需精简或延后辅助"])
    cores = [item for item in ingredients if item.role == "core"]
    supports = [item for item in ingredients if item.role == "support"]
    auxiliaries = [item for item in ingredients if item.role == "auxiliary"]
    primary = cores[0] if cores else (supports[0] if supports else None)
    support = supports[0] if supports and (not primary or supports[0].ingredient_id != primary.ingredient_id) else None
    auxiliary = auxiliaries[0] if auxiliaries else None
    b_days = set()
    if auxiliary and cycle_days == 10:
        b_days = set(TEN_DAY_B)
    elif auxiliary and cycle_days == 15:
        b_days = set(FIFTEEN_DAY_B)

    tasks: list[DailyTask] = []
    for day in range(1, cycle_days + 1):
        daily = _template_day(day, primary, support, auxiliary if day in b_days else None)
        _assert_daily_limits(daily, day)
        tasks.append(DailyTask(
            day=day,
            ingredients=daily,
            review=day in REVIEW_DAYS.get(cycle_days, set()),
            device_enabled=False,
            actual_device_seconds=0,
        ))
    return tasks, _exposure(tasks)


def build_extended_schedule(
    demands: list[IngredientDemand],
    *,
    cycle_days: int = 15,
) -> tuple[list[DailyTask], dict[str, dict[str, int]]]:
    if cycle_days not in {7, 10, 15}:
        raise ValueError("cycle_days must be 7, 10, or 15")
    required_slots = 0
    locked: dict[int, list[tuple[IngredientDemand, RegionCode]]] = {day: [] for day in range(1, cycle_days + 1)}
    for demand in demands:
        for region, days in demand.required_dates.items():
            region_code = RegionCode(region)
            for day in days:
                if day < 1 or day > cycle_days:
                    raise ScheduleInfeasibleError([f"{demand.ingredient_id} 锁定日期D{day}超出周期"])
                if day in demand.incompatible_dates:
                    raise ScheduleInfeasibleError([f"{demand.ingredient_id} 在D{day}既锁定又禁用"])
                locked[day].append((demand, region_code))
        for region, minimum in demand.minimum_days.items():
            required_slots += minimum
        if not demand.minimum_days and not demand.required_dates:
            required_slots += cycle_days

    capacity = cycle_days * FACE_DAILY_LIMIT
    if required_slots > capacity:
        raise ScheduleInfeasibleError([
            f"需要{required_slots}个成分日，但{cycle_days}天最多{capacity}个，返回容量冲突"
        ])

    tasks: list[DailyTask] = []
    for day in range(1, cycle_days + 1):
        grouped: dict[str, list[RegionCode]] = {}
        heads: dict[str, str] = {}
        region_locked: dict[RegionCode, list[str]] = {region: [] for region in RegionCode}
        for demand, region in locked[day]:
            grouped.setdefault(demand.ingredient_id, [])
            if region not in grouped[demand.ingredient_id]:
                grouped[demand.ingredient_id].append(region)
            heads[demand.ingredient_id] = demand.head_id or demand.ingredient_id
            region_locked[region].append(demand.ingredient_id)
        for region, ingredient_ids in region_locked.items():
            unique = list(dict.fromkeys(ingredient_ids))
            if len(unique) > REGION_DAILY_LIMIT:
                raise ScheduleInfeasibleError([
                    f"{region.value}区D{day}有{len(unique)}个锁定任务，不能删除锁定任务后宣布成功"
                ])
        daily = [
            DailyIngredientTask(
                ingredient_id=ingredient_id,
                head_id=heads[ingredient_id],
                regions=[region for region in REGION_ORDER if region in regions],
            )
            for ingredient_id, regions in grouped.items()
        ]
        if len(daily) > FACE_DAILY_LIMIT:
            raise ScheduleInfeasibleError([f"D{day}锁定成分超过全脸每日{FACE_DAILY_LIMIT}种"])
        tasks.append(DailyTask(
            day=day,
            ingredients=daily,
            review=day in REVIEW_DAYS.get(cycle_days, set()),
            device_enabled=False,
            actual_device_seconds=0,
        ))
    return tasks, _exposure(tasks)


def _template_day(
    day: int,
    primary: IngredientSelection | None,
    support: IngredientSelection | None,
    auxiliary: IngredientSelection | None,
) -> list[DailyIngredientTask]:
    if primary is None and support is None and auxiliary is None:
        return []
    a_regions = set(primary.regions) if primary else set()
    h_regions = set(support.regions) if support else set()
    b_regions = set(auxiliary.regions) if auxiliary else set()
    a_today: list[RegionCode] = []
    h_today: list[RegionCode] = []
    b_today: list[RegionCode] = []
    for region in REGION_ORDER:
        need_a = region in a_regions
        need_h = region in h_regions
        need_b = region in b_regions
        count = int(need_a) + int(need_h) + int(need_b)
        if count <= REGION_DAILY_LIMIT:
            if need_a:
                a_today.append(region)
            if need_h:
                h_today.append(region)
            if need_b:
                b_today.append(region)
            continue
        if need_h:
            h_today.append(region)
        if need_b:
            b_today.append(region)
        elif need_a:
            a_today.append(region)
    daily: list[DailyIngredientTask] = []
    if primary and a_today:
        daily.append(DailyIngredientTask(ingredient_id=primary.ingredient_id, head_id=primary.head_id, regions=a_today))
    if support and h_today:
        daily.append(DailyIngredientTask(ingredient_id=support.ingredient_id, head_id=support.head_id, regions=h_today))
    if auxiliary and b_today:
        daily.append(DailyIngredientTask(
            ingredient_id=auxiliary.ingredient_id,
            head_id=auxiliary.head_id,
            regions=b_today,
        ))
    return daily


def _assert_daily_limits(daily: list[DailyIngredientTask], day: int) -> None:
    if len(daily) > FACE_DAILY_LIMIT:
        raise ScheduleInfeasibleError([f"D{day}全脸超过{FACE_DAILY_LIMIT}种成分"])
    region_counts = {
        region: sum(region in item.regions for item in daily)
        for region in RegionCode
    }
    if any(count > REGION_DAILY_LIMIT for count in region_counts.values()):
        raise ScheduleInfeasibleError([f"D{day}单区超过{REGION_DAILY_LIMIT}种成分"])


def _exposure(tasks: list[DailyTask]) -> dict[str, dict[str, int]]:
    exposure: dict[str, dict[str, int]] = {}
    for task in tasks:
        for item in task.ingredients:
            exposure.setdefault(item.ingredient_id, {})
            for region in item.regions:
                key = region.value
                exposure[item.ingredient_id][key] = exposure[item.ingredient_id].get(key, 0) + 1
    return exposure
