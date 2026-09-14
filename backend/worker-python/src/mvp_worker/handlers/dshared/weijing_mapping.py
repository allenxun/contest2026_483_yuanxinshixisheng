"""shuiguang_cloud_v1 → weijing assess 请求/响应映射（隔离函数 + 批准钩子）。

本模块是**纯映射/校验**（无 DB、无网络、无 JobFailed 依赖），所有决策可单测。
适配器（``providers.LLMRagPlanAdapter``）在 PlanPort 边界内调用它，**只抛类型化异常**，
由 plan_generate 经既有 fenced terminal 机制落库。

红线（coordinator）：
- 绝不臆造参数/分数；``null``（不可评估）≠ 0；三视图计数**绝不相加**；
- 自然语言/非法结构绝不 ready；未获批准映射 → fail-closed；
- 真实失败绝不回退 mock。

请求映射（需 REQUEST_MAPPING 批准钩子）：把算法原始检测 JSON
（``schema_version=shuiguang_cloud_v1``）**有损**转换为 weijing assess 的 regions 形状：
- 区域仅 {forehead→F, left_cheek→L, right_cheek→R, chin→C}；``nose``/``perioral``
  丢弃（INFO 披露，其合同明确排除鼻部/未识别分区）。
- 检测项仅 {spots→P, surface_gloss→O}；``pores`` 在其合同无对应项（O/P/D 无毛孔）→
  丢弃披露。``surface_gloss≈O`` 是 **v2_oiliness_tendency** 口径的近似（含油光+卟啉
  证据，**不是**纯油光总分），随传必须注明。``D``（干燥性细纹）样本无来源 → 不发送。
- 分数只经**已注册** transform + score_source 产出：``invert_100_minus``
  （``score' = round_half_up(100 − score)``，int）与 ``global_front``（用检测的全局正面
  评分应用到各映射区域——本机制**可测**；其是否生产批准属总协调待决 N.2，见代码注释）。
- **计数不是分数**（不存在 count→score 路径）；``total_count``/``unassigned_count`` 只
  留在原始 JSON 存档路径，绝不进入请求分数。

输出映射（需 OUTPUT_MAPPING 批准钩子）：``WeijingPlan`` 不含我方冻结
plan_payload 所需的任何真实设备参数，未批准前 :func:`plan_to_candidate` 直接终态
拒绝，**绝不半构造**、绝不把 rendered_markdown 自然语言标 ready。
"""
from __future__ import annotations

import logging
import math
from typing import Any, Callable, Optional

log = logging.getLogger("mvp_worker.handlers.dshared.weijing_mapping")

# --- 合同固定枚举 ---
SCHEMA_VERSION = "shuiguang_cloud_v1"
SEVERITIES = ("未见明显", "轻度", "中度", "较明显", "显著")
WEIJING_PLAN_STATUSES = (
    "READY_CARE",
    "PREVIEW_ONLY",
    "REVIEW_REQUIRED",
    "PAUSED",
    "URGENT",
    "SCHEDULE_INFEASIBLE",
)
VIEWS = ("left", "front", "right")
REGION_ENUM = ("forehead", "nose", "left_cheek", "right_cheek", "perioral", "chin")
_RAW_TOP_KEYS = frozenset(
    {"schema_version", "task_id", "status", "main_image_id", "views", "results"}
)
_RAW_RESULT_KEYS = frozenset({"pores", "spots", "surface_gloss"})
# 每项检测的 score_basis 必须为 item-specific 字面量（防错项口径混入）。
SCORE_BASIS_BY_ITEM = {
    "pores": "v2_visible_pores",
    "spots": "v2_visible_spots_component",
    "surface_gloss": "v2_oiliness_tendency",
}
_DETECTION_KEYS = frozenset(
    {"name", "score", "severity", "score_view", "score_basis",
     "total_count", "regions", "unassigned_count"}
)
_REGION_KEYS = frozenset(
    {"region", "name", "left", "front", "right",
     "primary_view", "primary_count", "supplementary_views"}
)

# 区域/检测项映射（其余丢弃 → INFO 披露）。
REGION_MAP: dict[str, str] = {
    "forehead": "F",
    "left_cheek": "L",
    "right_cheek": "R",
    "chin": "C",
}
ITEM_MAP: dict[str, str] = {"spots": "P", "surface_gloss": "O"}
DROPPED_REGIONS = ("nose", "perioral")
DROPPED_ITEMS = ("pores",)
# surface_gloss→O 的口径近似（必须随传注明；不得描述成纯油光总分）。
SURFACE_GLOSS_IS_OILINESS_TENDENCY_NOTE = (
    "surface_gloss 沿用 v2_oiliness_tendency 口径（含油光+卟啉证据），非纯油光总分"
)

# REQUEST_MAPPING 批准钩子识别的已注册算子（批准配置只能引用这些名字）。
_TRANSFORMS: dict[str, Callable[[float], float]] = {}


class MappingNotApproved(RuntimeError):
    """映射未获批准（env 钩子未设 / 引用未注册算子）→ 适配器落终态，绝不臆造。"""


class RawDetectionContractViolation(RuntimeError):
    """算法原始检测 JSON 违反 shuiguang_cloud_v1 合同（含跨字段不变量）。"""


class ResponseContractViolation(RuntimeError):
    """weijing assess 响应违反封闭结构合同。"""


class PlanProviderConfigRequired(RuntimeError):
    """weijing assess 鉴权/配置拒绝（AI_UNAUTHORIZED）→ 终态 PLAN_PROVIDER_CONFIG。"""


def _round_half_up(value: float) -> int:
    """四舍五入（half-up，非银行家舍入）。"""
    return int(math.floor(float(value) + 0.5))


def _transform_invert_100_minus(value: float) -> float:
    """score' = 100 − score（样本方向：越高越明显 → 请求方向：越高越好）。"""
    return 100.0 - float(value)


_TRANSFORMS["invert_100_minus"] = _transform_invert_100_minus
_ROUNDINGS: dict[str, Callable[[float], int]] = {"half_up": _round_half_up}


def _source_global_front(raw: dict[str, Any], item_name: str, region_name: str) -> Optional[float]:
    """score_source=global_front：用检测项全局正面评分（应用到各映射区域）。

    NOTE：把全局 front 分复制到各分区属**分区粒度缺失**下的受控近似；本机制为
    测试可执行路径，**是否生产批准属总协调待决 N.2**——未获书面口径前，env 钩子
    缺省未设，适配器 fail-closed。
    """
    return raw["results"][item_name]["score"]


_SCORE_SOURCES: dict[
    str, Callable[[dict[str, Any], str, str], Optional[float]]
] = {"global_front": _source_global_front}


def _approved_request_mapping(request_mapping: Any) -> dict[str, str]:
    """校验 REQUEST_MAPPING 批准配置；未设/引用未注册算子 → MappingNotApproved。"""
    if not isinstance(request_mapping, dict) or not request_mapping:
        raise MappingNotApproved(
            "weijing request mapping not approved: MVP_D_LLM_RAG_REQUEST_MAPPING unset"
            " (coordination N.2 pending); refusing to fabricate scores"
        )
    allowed = {"score_transform", "rounding", "score_source"}
    extra = set(request_mapping) - allowed
    if extra:
        raise MappingNotApproved(
            f"weijing request mapping has unapproved keys: {sorted(extra)}"
        )
    missing = allowed - set(request_mapping)
    if missing:
        raise MappingNotApproved(
            f"weijing request mapping incomplete; missing {sorted(missing)} (coordination N.2)"
        )
    if request_mapping["score_transform"] not in _TRANSFORMS:
        raise MappingNotApproved("weijing request mapping references unregistered transform")
    if request_mapping["rounding"] not in _ROUNDINGS:
        raise MappingNotApproved("weijing request mapping references unregistered rounding")
    if request_mapping["score_source"] not in _SCORE_SOURCES:
        raise MappingNotApproved("weijing request mapping references unregistered score_source")
    return request_mapping


# ---------------------------------------------------------------- raw validation


def _is_count(value: Any) -> bool:
    """严格非负整数或 None（bool/float 拒绝）。"""
    return value is None or (
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
    )


def _is_score(value: Any) -> bool:
    """float|int 0..100 或 None（bool 拒绝）。"""
    return value is None or (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0.0 <= float(value) <= 100.0
    )


def _validate_count_map(value: Any, label: str) -> None:
    if not isinstance(value, dict) or set(value) != set(VIEWS):
        raise RawDetectionContractViolation(f"{label} keys invalid")
    for view in VIEWS:
        if not _is_count(value[view]):
            raise RawDetectionContractViolation(f"{label}.{view} invalid")


def validate_raw_detection(raw: Any) -> None:
    """封闭校验算法原始检测 JSON（shuiguang_cloud_v1 合同草稿 + 跨字段不变量）。

    形状参考：用户授权 fixture ``response_models.reference.py``（**绝不 import**）与
    ``字段说明.md``。任何违反 → :class:`RawDetectionContractViolation`（调用方落终态
    PROVIDER_CONTRACT_VIOLATION），绝不发请求/臆造。
    """
    if not isinstance(raw, dict):
        raise RawDetectionContractViolation("raw detection is not an object")
    if set(raw) != _RAW_TOP_KEYS:
        raise RawDetectionContractViolation(
            f"raw detection top-level keys invalid: {sorted(set(raw) ^ _RAW_TOP_KEYS)}"
        )
    if raw["schema_version"] != SCHEMA_VERSION:
        raise RawDetectionContractViolation("raw detection schema_version mismatch")
    if not isinstance(raw["task_id"], str) or not raw["task_id"]:
        raise RawDetectionContractViolation("raw detection task_id invalid")
    if raw["status"] != "success":
        raise RawDetectionContractViolation("raw detection status is not success")
    if not isinstance(raw["main_image_id"], str) or not raw["main_image_id"]:
        raise RawDetectionContractViolation("raw detection main_image_id invalid")

    views = raw["views"]
    if (
        not isinstance(views, dict)
        or set(views) != set(VIEWS)
        or not all(isinstance(views[v], str) and views[v] for v in VIEWS)
    ):
        raise RawDetectionContractViolation("raw detection views invalid")
    if raw["main_image_id"] != views["front"]:
        raise RawDetectionContractViolation("raw detection main_image_id != views.front")

    results = raw["results"]
    if not isinstance(results, dict) or set(results) != _RAW_RESULT_KEYS:
        raise RawDetectionContractViolation("raw detection results keys invalid")

    for item_name in _RAW_RESULT_KEYS:
        _validate_detection(item_name, results[item_name])


def _validate_detection(item_name: str, item: Any) -> None:
    label = f"results.{item_name}"
    if not isinstance(item, dict) or set(item) != _DETECTION_KEYS:
        raise RawDetectionContractViolation(f"{label} keys invalid")
    if not isinstance(item["name"], str):
        raise RawDetectionContractViolation(f"{label}.name invalid")
    if not _is_score(item["score"]):
        raise RawDetectionContractViolation(f"{label}.score invalid")
    severity = item["severity"]
    if severity is not None and severity not in SEVERITIES:
        raise RawDetectionContractViolation(f"{label}.severity invalid")
    # 跨字段：score None ⇔ severity None。
    if (item["score"] is None) != (severity is None):
        raise RawDetectionContractViolation(f"{label}: score/severity null mismatch")
    if item["score_view"] != "front":
        raise RawDetectionContractViolation(f"{label}.score_view must be 'front'")
    if item["score_basis"] != SCORE_BASIS_BY_ITEM[item_name]:
        raise RawDetectionContractViolation(f"{label}.score_basis invalid for item")

    _validate_count_map(item["total_count"], f"{label}.total_count")
    _validate_count_map(item["unassigned_count"], f"{label}.unassigned_count")

    regions = item["regions"]
    if not isinstance(regions, list) or not regions:
        raise RawDetectionContractViolation(f"{label}.regions must be a non-empty list")
    for i, region in enumerate(regions):
        _validate_region(f"{label}.regions[{i}]", region)

    # 跨字段：逐视图对账（sum(区域计数) + unassigned == total）。
    for view in VIEWS:
        total = item["total_count"][view]
        if total is None:
            continue
        unassigned = item["unassigned_count"][view]
        if unassigned is None:
            raise RawDetectionContractViolation(
                f"{label}: unassigned_count[{view}] null while total_count non-null"
            )
        region_sum = sum(r[view] for r in regions if r[view] is not None)
        if region_sum + unassigned != total:  # type: ignore[operator]
            raise RawDetectionContractViolation(
                f"{label}: per-view reconciliation failed for {view}"
            )


def _validate_region(label: str, region: Any) -> None:
    if not isinstance(region, dict) or set(region) != _REGION_KEYS:
        raise RawDetectionContractViolation(f"{label} keys invalid")
    if region["region"] not in REGION_ENUM:
        raise RawDetectionContractViolation(f"{label}.region unknown")
    if not isinstance(region["name"], str):
        raise RawDetectionContractViolation(f"{label}.name invalid")
    for view in VIEWS:
        if not _is_count(region[view]):
            raise RawDetectionContractViolation(f"{label}.{view} invalid")
    primary_view = region["primary_view"]
    primary_count = region["primary_count"]
    if primary_view is not None and primary_view not in VIEWS:
        raise RawDetectionContractViolation(f"{label}.primary_view invalid")
    if not _is_count(primary_count):
        raise RawDetectionContractViolation(f"{label}.primary_count invalid")
    # 跨字段：primary_view None ⇔ primary_count None；primary_count == row[primary_view]。
    if (primary_view is None) != (primary_count is None):
        raise RawDetectionContractViolation(f"{label}: primary_view/primary_count null mismatch")
    if primary_view is not None and primary_count != region[primary_view]:
        raise RawDetectionContractViolation(f"{label}.primary_count != row[primary_view]")
    supplementary = region["supplementary_views"]
    if not isinstance(supplementary, list) or not all(
        isinstance(v, str) and v in VIEWS for v in supplementary
    ):
        raise RawDetectionContractViolation(f"{label}.supplementary_views invalid")


def build_request(
    report_context: dict[str, Any],
    input_snapshot: dict[str, Any],
    *,
    request_mapping: Any,
) -> dict[str, Any]:
    """构造 weijing assess 请求体（regions 形状）。fail-closed；绝不臆造分数。"""
    raw = report_context.get("raw_detection") if isinstance(report_context, dict) else None
    if raw is None:
        raise MappingNotApproved(
            "raw algorithm detection JSON not present in report_context; approved capture"
            " path pending (coordination N.4)"
        )
    validate_raw_detection(raw)
    approved = _approved_request_mapping(request_mapping)
    transform_fn = _TRANSFORMS[approved["score_transform"]]
    rounding_fn = _ROUNDINGS[approved["rounding"]]
    source_fn = _SCORE_SOURCES[approved["score_source"]]

    log.info(
        "weijing.map.disclosure dropped_regions=%s dropped_items=%s note=%s",
        list(DROPPED_REGIONS), list(DROPPED_ITEMS), SURFACE_GLOSS_IS_OILINESS_TENDENCY_NOTE,
    )

    regions: dict[str, dict[str, int]] = {}
    for item_name, item_code in ITEM_MAP.items():
        for region_name, region_code in REGION_MAP.items():
            raw_score = source_fn(raw, item_name, region_name)
            if raw_score is None:
                continue  # null = 不可评估 → 省略该 concern（绝不写 0）
            regions.setdefault(region_code, {})[item_code] = rounding_fn(transform_fn(raw_score))

    report = input_snapshot.get("report") if isinstance(input_snapshot, dict) else None
    report_id = report.get("report_id") if isinstance(report, dict) else None
    body: dict[str, Any] = {
        "report_id": report_id,
        "algorithm_version": SCHEMA_VERSION,
        "regions": regions,
    }
    device_id = report_context.get("device_id") if isinstance(report_context, dict) else None
    if isinstance(device_id, str) and device_id.strip():
        body["device_id"] = device_id
    return body


# ---------------------------------------------------------------- response validation


def validate_envelope(payload: Any) -> None:
    """封闭校验 2xx 成功信封。"""
    if not isinstance(payload, dict):
        raise ResponseContractViolation("weijing response is not an object")
    expected = {"request_id", "invocation_id", "spoken_text", "assessment", "continuation_state"}
    if set(payload) != expected:
        raise ResponseContractViolation(
            f"weijing envelope keys invalid: {sorted(set(payload) ^ expected)}"
        )
    for key in ("request_id", "invocation_id"):
        if not isinstance(payload[key], str) or not payload[key]:
            raise ResponseContractViolation(f"weijing envelope {key} invalid")
    if not isinstance(payload["spoken_text"], str):
        raise ResponseContractViolation("weijing envelope spoken_text not a string")
    if not isinstance(payload["assessment"], dict):
        raise ResponseContractViolation("weijing envelope assessment not an object")
    if payload["continuation_state"] is not None and not isinstance(
        payload["continuation_state"], dict
    ):
        raise ResponseContractViolation("weijing envelope continuation_state invalid")


def validate_assessment(assessment: Any) -> None:
    """校验 assessment 必需子集（设备字段原样，不重解释）。"""
    if not isinstance(assessment, dict):
        raise ResponseContractViolation("weijing assessment not an object")
    if not isinstance(assessment.get("assessment_id"), str) or not assessment["assessment_id"]:
        raise ResponseContractViolation("weijing assessment_id missing")
    if assessment.get("created_at") is None:
        raise ResponseContractViolation("weijing assessment created_at missing")
    if not isinstance(assessment.get("rendered_markdown"), str):
        raise ResponseContractViolation("weijing assessment rendered_markdown not a string")
    plan = assessment.get("plan")
    if not isinstance(plan, dict):
        raise ResponseContractViolation("weijing assessment plan not an object")
    if not isinstance(plan.get("plan_id"), str) or not plan["plan_id"]:
        raise ResponseContractViolation("weijing plan_id missing")
    if plan.get("status") not in WEIJING_PLAN_STATUSES:
        raise ResponseContractViolation("weijing plan status unknown")
    if not isinstance(plan.get("knowledge_version"), str) or not plan["knowledge_version"]:
        raise ResponseContractViolation("weijing plan knowledge_version missing")


# OUTPUT_MAPPING 批准钩子：当前**零注册**（无批准输出映射）→ 任何配置也 fail-closed。
_OUTPUT_MAPPINGS: dict[str, Callable[[dict[str, Any]], Any]] = {}


def plan_to_candidate(assessment: dict[str, Any], *, output_mapping: Any) -> Any:
    """把 WeijingPlan 映射为我方候选。无批准映射 → MappingNotApproved 终态。

    ``WeijingPlan`` 不含 intensity/duration/pulse_count/target_count 的真实对应；
    未获批准前绝不半构造（coordinator N.3）。
    """
    if not isinstance(output_mapping, dict) or not output_mapping:
        raise MappingNotApproved(
            "weijing plan structurally valid; no approved mapping to the frozen"
            " device-parameter plan contract; coordination N.3"
        )
    mapping_id = output_mapping.get("mapping_id")
    fn = _OUTPUT_MAPPINGS.get(mapping_id) if isinstance(mapping_id, str) else None
    if fn is None:
        raise MappingNotApproved(
            "weijing output mapping not registered/approved; coordination N.3"
        )
    return fn(assessment)
