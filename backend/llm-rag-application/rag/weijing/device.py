from __future__ import annotations

from rag.weijing.catalog import load_catalog
from rag.weijing.models import DeviceAssignment, RegionCode, Severity


def sim_region_budget(region: RegionCode | str, severity: Severity | str) -> int:
    catalog = load_catalog()["sim_preview"]
    region_key = region.value if isinstance(region, RegionCode) else region
    severity_key = severity.value if isinstance(severity, Severity) else severity
    cap = catalog["region_caps"][region_key]
    coeff = catalog["coefficients"].get(severity_key, 0)
    return int(cap * coeff)


def validate_device_allocation(
    assignments: list[DeviceAssignment] | list[dict],
    *,
    region_caps: dict[str, int],
    face_cap: int,
    local_caps: dict[str, int] | None = None,
) -> list[str]:
    region_totals: dict[str, int] = {}
    local_totals: dict[str, int] = {}
    conflicts: list[str] = []
    for item in assignments:
        if isinstance(item, DeviceAssignment):
            region = item.region.value
            head_id = item.head_id
            seconds = item.seconds
        else:
            region = str(item["region"])
            head_id = str(item.get("head_id") or "")
            seconds = int(item["seconds"])
        region_totals[region] = region_totals.get(region, 0) + seconds
        local_key = str(item.get("point_id") if isinstance(item, dict) else f"{region}:{head_id}")
        if isinstance(item, dict) and item.get("point_id"):
            local_key = str(item["point_id"])
            local_totals[local_key] = local_totals.get(local_key, 0) + seconds
    for region, total in region_totals.items():
        cap = region_caps.get(region)
        if cap is not None and total > cap:
            conflicts.append(f"{region}区设备时长{total}秒超过上限{cap}秒")
    face_total = sum(region_totals.values())
    if face_total > face_cap:
        conflicts.append(f"全脸设备时长{face_total}秒超过上限{face_cap}秒")
    for point_id, total in local_totals.items():
        cap = (local_caps or {}).get(point_id)
        if cap is not None and total > cap:
            conflicts.append(f"局部{point_id}停留{total}秒超过上限{cap}秒")
    return conflicts


def actual_device_seconds(profile_status: str, allocation_rules_confirmed: bool) -> int:
    if profile_status != "VALIDATED" or not allocation_rules_confirmed:
        return 0
    return 0


def interval_conflict(last_device_hours_ago: int | None, min_interval_hours: int | None) -> bool:
    if last_device_hours_ago is None or min_interval_hours is None:
        return False
    return last_device_hours_ago < min_interval_hours
