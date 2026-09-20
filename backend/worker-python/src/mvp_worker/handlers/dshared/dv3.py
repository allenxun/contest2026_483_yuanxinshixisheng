"""V3 三组评分（``pores``/``spots``/``surface_gloss``）严格校验的**单一事实源**。

被两处复用，语义必须完全一致：

- ``assessment_analyze._validate_v3_skin_groups``（发布前防御式复校验）；
- ``dshuiguang.ShuiguangSkinAdapter``（真实服务返回体进入 Worker 前的首道校验）。

规则（coordinator §688 收紧后）：顶层恰三组键（all-or-none）；每组/每区域闭合键白名单；
``score`` 为 ``null``（缺测）或 **非 float 强转** 的 0..100（巨大整数/inf/nan 一律违约）；
``severity`` 为 ``null`` 或冻结词表；``name``/``region`` 非空白且**逐字保留（不 trim）**；
``regions`` **非空**且组内 ``region`` 唯一。任何违约 → :class:`V3SkinViolation`
（由调用方映射为终态 ``PROVIDER_CONTRACT_VIOLATION`` 或输入违约）。**绝不**把 null 变 0，
绝不补区、绝不做画面/本人左右转换。
"""
from __future__ import annotations

from typing import Any, Optional

from .dskin_mock import V3_SKIN_GROUP_KEYS, V3_SKIN_SEVERITIES


class V3SkinViolation(RuntimeError):
    """V3 三组校验失败（确定性）→ 终态/输入违约，绝不当瞬时故障重试。"""


def validate_v3_skin_groups(raw: Any) -> Optional[dict[str, Any]]:
    """``None`` 原样返回；否则返回仅含白名单键的**规范化深拷贝**；违约抛异常。"""
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != set(V3_SKIN_GROUP_KEYS):
        raise V3SkinViolation(
            "$.v3_skin: expected exactly pores/spots/surface_gloss (all-or-none)"
        )
    group_allowed = {"score", "severity", "name", "regions"}
    region_allowed = {"region", "name", "score", "severity"}
    normalized: dict[str, Any] = {}
    for group_key in V3_SKIN_GROUP_KEYS:
        group = raw[group_key]
        if not isinstance(group, dict):
            raise V3SkinViolation(f"$.{group_key}: expected object")
        if set(group) - group_allowed:
            raise V3SkinViolation(f"$.{group_key}: additionalProperties violated")
        for required in ("score", "severity", "name", "regions"):
            if required not in group:
                raise V3SkinViolation(f"$.{group_key}.{required}: required")
        score = group["score"]
        if score is not None and (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not (0 <= score <= 100)
        ):
            raise V3SkinViolation(f"$.{group_key}.score: type/range violated")
        severity = group["severity"]
        if severity is not None and severity not in V3_SKIN_SEVERITIES:
            raise V3SkinViolation(f"$.{group_key}.severity: not in frozen vocabulary")
        name = group["name"]
        if not isinstance(name, str) or not name.strip():
            raise V3SkinViolation(f"$.{group_key}.name: non-blank string required")
        regions = group["regions"]
        if not isinstance(regions, list):
            raise V3SkinViolation(f"$.{group_key}.regions: expected array")
        if not regions:
            raise V3SkinViolation(f"$.{group_key}.regions: non-empty array required")
        seen_regions: set[str] = set()
        out_regions: list[dict[str, Any]] = []
        for i, item in enumerate(regions):
            if not isinstance(item, dict):
                raise V3SkinViolation(f"$.{group_key}.regions[{i}]: expected object")
            if set(item) - region_allowed:
                raise V3SkinViolation(
                    f"$.{group_key}.regions[{i}]: additionalProperties violated"
                )
            for required in ("region", "name", "score", "severity"):
                if required not in item:
                    raise V3SkinViolation(
                        f"$.{group_key}.regions[{i}].{required}: required"
                    )
            region = item["region"]
            if not isinstance(region, str) or not region.strip():
                raise V3SkinViolation(
                    f"$.{group_key}.regions[{i}].region: non-blank string required"
                )
            if region in seen_regions:
                raise V3SkinViolation(
                    f"$.{group_key}.regions[{i}].region: duplicate region"
                )
            seen_regions.add(region)
            region_name = item["name"]
            if not isinstance(region_name, str) or not region_name.strip():
                raise V3SkinViolation(
                    f"$.{group_key}.regions[{i}].name: non-blank string required"
                )
            region_score = item["score"]
            if region_score is not None and (
                not isinstance(region_score, (int, float))
                or isinstance(region_score, bool)
                or not (0 <= region_score <= 100)
            ):
                raise V3SkinViolation(
                    f"$.{group_key}.regions[{i}].score: type/range violated"
                )
            region_severity = item["severity"]
            if region_severity is not None and region_severity not in V3_SKIN_SEVERITIES:
                raise V3SkinViolation(
                    f"$.{group_key}.regions[{i}].severity: not in frozen vocabulary"
                )
            out_regions.append(
                {
                    "region": region,
                    "name": region_name,
                    "score": region_score,
                    "severity": region_severity,
                }
            )
        normalized[group_key] = {
            "score": score,
            "severity": severity,
            "name": name,
            "regions": out_regions,
        }
    return normalized
