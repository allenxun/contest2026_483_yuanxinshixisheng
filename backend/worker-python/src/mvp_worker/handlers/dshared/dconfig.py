"""D 包 env 配置与受控基线（MVP 明确标注为占位/待设备团队批准）。

env 一览（全部可选，dev 初值仅为联调起点，非验收硬值）：

| env | 默认 | 说明 |
|---|---|---|
| ``MVP_D_FACE_PROVIDER`` | ``double`` | double / aliyun_face |
| ``MVP_D_SKIN_PROVIDER`` | ``double`` | double / aliyun_skin |
| ``MVP_D_PLAN_PROVIDER`` | ``double`` | double / aliyun_llm |
| ``MVP_IDENTITY_NAMESPACE`` | ``mvp-ns-1`` | 人脸库命名空间 |
| ``MVP_D_PROVIDER_CONFIG_REVISION`` | ``1`` | 供应商配置代次（对账用） |
| ``MVP_D_RESULT_IMAGE_MAX_BYTES`` | ``10485760`` | 结果图大小上限（10MiB） |
| ``MVP_SKIN_METRICS_BASELINE`` | 内置受控基线 | JSON；指标白名单（name/unit/min/max） |
| ``MVP_PLAN_CAPABILITY_BASELINE`` | 内置受控基线 | JSON；能力/参数范围/批准区域/N 边界 |
| ``MVP_PLAN_CAPABILITY_STALE_SECONDS`` | ``86400`` | T04 观察新鲜窗口；0=忽略 |
| ``MVP_PLAN_WAIT_CHECK_SECONDS`` | ``30`` | 能力待补齐的 defer 再检查间隔（合法等待态，不消耗 attempt） |
| ``MVP_D_PLAN_PROMPT_VERSION`` | ``1`` | 方案提示模板版本 |
| ``MVP_D_FACE_DOUBLE_QUALITY`` | ``accepted`` | 测试注入：face 质量（``accepted``/``needs_retake``；后者可配 required views） |
| ``MVP_D_FACE_DOUBLE_REQUIRED_VIEWS`` | 空 | 测试注入：逗号分隔补拍视角（仅 ``front``/``left``/``right`` 子集；空=替身默认） |
| ``MVP_D_FACE_DOUBLE_SAME_PERSON`` | ``true`` | 测试注入：同人判定（``false`` → NOT_SAME_PERSON） |
| ``MVP_D_FACE_DOUBLE_SEARCH`` | ``reliable_new`` | 测试注入：1:N 分类（``reliable_new``/``matched``/``uncertain``/``ambiguous``/``dependency_failed``） |
| ``MVP_D_SKIN_DOUBLE_HOLD`` | ``false`` | 测试注入：进程级 hold（analyze 可重试失败，旧执行停在 queued，可释放） |
| ``MVP_D_PLAN_DOUBLE_MODE`` | ``valid`` | 测试注入：``valid``/``timeout``/``failure`` 或 PlanDouble 既有非法形状名 |
| ``MVP_D_STORAGE_DOUBLE_FAIL_PUT`` | ``false`` | 测试注入：``assessment_result`` 用途 put 受控失败（可重试 RESULT_ARCHIVE_FAILED） |
| ``MVP_D_ALIYUN_ACTIVATED`` | ``false`` | 阿里云适配器真实激活开关（需凭据 + PoC） |
| ``MVP_D_ALIYUN_ENDPOINT`` / ``_ACCESS_KEY_ID`` / ``_ACCESS_KEY_SECRET`` | 未设 | 阿里云凭据（只走 env，绝不入仓） |
| ``MVP_D_ALIYUN_FACE_DB_NAME`` / ``MVP_D_ALIYUN_LLM_MODEL`` | 未设 | 人脸库 DbName / 大模型名 |

**基线是 MVP 受控占位**：真实设备协议/指标口径待设备团队批准；代码只信任这里
列出的白名单，绝不发布未批准指标/区域/参数。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from ...media.storage import (
    STORAGE_DOUBLE_FAIL_PUT_ENV,
    storage_put_failure_injected,
)
from .constants import REQUIRED_VIEWS_ALL


class ProviderConfigError(RuntimeError):
    """配置错误（生产解析到替身 / 非法注入取值 / 生产出现注入开关）。

    定义在配置模块以避免 ``providers`` 的循环依赖；``providers`` 重新导出同名符号，
    既有 ``from ...providers import ProviderConfigError`` 保持可用。
    """


DEFAULT_FACE_PROVIDER = "double"
DEFAULT_SKIN_PROVIDER = "double"
DEFAULT_PLAN_PROVIDER = "double"
DEFAULT_IDENTITY_NAMESPACE = "mvp-ns-1"
DEFAULT_PROVIDER_CONFIG_REVISION = "1"
DEFAULT_RESULT_IMAGE_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_PLAN_CAPABILITY_STALE_SECONDS = 86400
DEFAULT_PLAN_WAIT_CHECK_SECONDS = 30
DEFAULT_PROMPT_TEMPLATE_VERSION = "1"

# --- 测试替身注入（默认值 = 当前行为 = 不注入；仅读 double 分支，生产 fail-closed） ---
DEFAULT_FACE_DOUBLE_QUALITY = "accepted"
DEFAULT_FACE_DOUBLE_SEARCH = "reliable_new"
DEFAULT_PLAN_DOUBLE_MODE = "valid"
DEFAULT_SKIN_DOUBLE_HOLD = False

FACE_DOUBLE_QUALITY_MODES = ("accepted", "needs_retake")
FACE_DOUBLE_SEARCH_MODES = (
    "reliable_new",
    "matched",
    "uncertain",
    "ambiguous",
    "dependency_failed",
)
# PlanDouble._apply_invalid 的既有非法形状名（与 providers.PlanDouble 一一对应）。
PLAN_DOUBLE_INVALID_MODES = (
    "n_zero",
    "n_too_large",
    "n_string_garbage",
    "n_string_ok",
    "empty_steps",
    "unknown_region",
    "param_out_of_range",
    "unknown_param",
    "extra_property",
    "bad_parameters_shape",
)
PLAN_DOUBLE_FAILURE_MODES = ("valid", "timeout", "failure")
PLAN_DOUBLE_MODES = PLAN_DOUBLE_FAILURE_MODES + PLAN_DOUBLE_INVALID_MODES

#: 本批注入开关 → 默认（语义）值；用于生产 fail-closed 判定（显式非默认才算注入）。
DOUBLE_INJECTION_SWITCHES: dict[str, Any] = {
    "MVP_D_FACE_DOUBLE_QUALITY": DEFAULT_FACE_DOUBLE_QUALITY,
    "MVP_D_FACE_DOUBLE_REQUIRED_VIEWS": (),
    "MVP_D_FACE_DOUBLE_SAME_PERSON": True,
    "MVP_D_FACE_DOUBLE_SEARCH": DEFAULT_FACE_DOUBLE_SEARCH,
    "MVP_D_PLAN_DOUBLE_MODE": DEFAULT_PLAN_DOUBLE_MODE,
    "MVP_D_SKIN_DOUBLE_HOLD": DEFAULT_SKIN_DOUBLE_HOLD,
    STORAGE_DOUBLE_FAIL_PUT_ENV: False,
}
_BOOLEAN_INJECTION_SWITCHES = frozenset(
    {
        "MVP_D_FACE_DOUBLE_SAME_PERSON",
        "MVP_D_SKIN_DOUBLE_HOLD",
        STORAGE_DOUBLE_FAIL_PUT_ENV,
    }
)

# MVP 受控测肤指标基线（占位；待设备/算法团队批准的口径替换）。
DEFAULT_SKIN_METRICS_BASELINE: dict[str, Any] = {
    "schema_version": 1,
    "metrics": [
        {"name": "moisture", "unit": "percent", "min": 0.0, "max": 100.0},
        {"name": "oiliness", "unit": "percent", "min": 0.0, "max": 100.0},
        {"name": "smoothness", "unit": "score", "min": 0.0, "max": 100.0},
        {"name": "redness", "unit": "score", "min": 0.0, "max": 100.0},
    ],
}

# MVP 受控能力基线（占位；真实微晶协议待设备团队批准，参数范围仅示例）。
DEFAULT_PLAN_CAPABILITY_BASELINE: dict[str, Any] = {
    "schema_version": 1,
    "capability_id": "mvp-double-capability",
    "revision": 1,
    "parameter_ranges": {
        "intensity": {"unit": "percent", "min": 0.0, "max": 100.0},
        "duration": {"unit": "second", "min": 1.0, "max": 600.0},
        "pulse_count": {"unit": "count", "min": 1.0, "max": 1000.0},
    },
    "approved_regions": ["forehead", "left_cheek", "right_cheek", "nose"],
    "n_bounds": {"min": 1, "max": 100},
}


def _env(name: str, default: str) -> str:
    raw = os.environ.get(name, "").strip()
    return raw if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_list(name: str) -> tuple[str, ...]:
    """逗号分隔清单；缺省/空 → ()（= 使用替身自身默认）。"""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def double_injection_overrides() -> dict[str, str]:
    """返回被**显式设为非默认语义值**的注入开关（缺失/默认值不算）。

    布尔开关按语义比较（``0/no/off`` 与默认 false 等价），避免误判为注入。
    """
    overrides: dict[str, str] = {}
    for name, default in DOUBLE_INJECTION_SWITCHES.items():
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        if name in _BOOLEAN_INJECTION_SWITCHES:
            if (raw.lower() in ("1", "true", "yes", "on")) != bool(default):
                overrides[name] = raw
        elif name == "MVP_D_FACE_DOUBLE_REQUIRED_VIEWS":
            overrides[name] = raw  # 非空即非默认
        elif raw.lower() != str(default).lower():
            overrides[name] = raw
    return overrides


def production_environment_signals() -> list[str]:
    """返回所有"生产信号"（任一成立即视为生产，覆盖混合/矛盾组合）。

    含：解析后环境（沿用 notifications.config 优先级）、``MVP_NOTIFY_ENV`` /
    ``MVP_WORKER_ENVIRONMENT`` / ``APP_ENV`` 任一显式为 production/prod（即使被
    更高优先级覆盖成 dev）、以及 active Spring profile 含 prod/production。
    """
    signals: list[str] = []
    try:
        from ...notifications.config import resolve_environment

        resolved = resolve_environment()
    except Exception:  # pragma: no cover - 极端导入环境
        resolved = os.environ.get("APP_ENV", "dev").strip().lower()
    if resolved in ("production", "prod"):
        signals.append(f"resolved_environment={resolved}")
    for name in ("MVP_NOTIFY_ENV", "MVP_WORKER_ENVIRONMENT", "APP_ENV"):
        raw = os.environ.get(name, "").strip().lower()
        if raw in ("production", "prod"):
            signals.append(f"{name}={raw}")
    profiles = os.environ.get("SPRING_PROFILES_ACTIVE", "")
    if any(p.strip().lower() in ("prod", "production") for p in profiles.split(",") if p.strip()):
        signals.append(f"SPRING_PROFILES_ACTIVE={profiles.strip()}")
    return signals


def assert_no_double_injection_in_production() -> None:
    """始终生效的生产 fail-closed 守卫（加载/启动即校验）。

    仅当存在生产信号**且**任一注入开关被显式设为非默认值时拒绝启动；与既有
    ``providers._forbid_double_in_production``（provider=double 在生产被拒）互补，
    不重复报错：本守卫专门拦截"注入了故障替身"的配置，错误信息列出信号与开关。
    """
    overrides = double_injection_overrides()
    if not overrides:
        return
    signals = production_environment_signals()
    if not signals:
        return
    raise ProviderConfigError(
        "production fail-closed: test-double injection switches set in a production"
        f" context (signals: {signals}; switches: {sorted(overrides)}); refusing to start"
    )


def _env_json(name: str, default: dict[str, Any]) -> dict[str, Any]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return json.loads(json.dumps(default))  # deep copy
    if raw.lower() in ("none", "null", "false"):
        return {}
    return json.loads(raw)


def _env_optional_json(name: str, default: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return json.loads(json.dumps(default)) if default is not None else None
    if raw.lower() in ("none", "null", "false"):
        return None
    return json.loads(raw)


@dataclass(frozen=True)
class DConfig:
    face_provider: str = field(
        default_factory=lambda: _env("MVP_D_FACE_PROVIDER", DEFAULT_FACE_PROVIDER)
    )
    skin_provider: str = field(
        default_factory=lambda: _env("MVP_D_SKIN_PROVIDER", DEFAULT_SKIN_PROVIDER)
    )
    plan_provider: str = field(
        default_factory=lambda: _env("MVP_D_PLAN_PROVIDER", DEFAULT_PLAN_PROVIDER)
    )
    identity_namespace: str = field(
        default_factory=lambda: _env("MVP_IDENTITY_NAMESPACE", DEFAULT_IDENTITY_NAMESPACE)
    )
    provider_config_revision: str = field(
        default_factory=lambda: _env(
            "MVP_D_PROVIDER_CONFIG_REVISION", DEFAULT_PROVIDER_CONFIG_REVISION
        )
    )
    result_image_max_bytes: int = field(
        default_factory=lambda: _env_int(
            "MVP_D_RESULT_IMAGE_MAX_BYTES", DEFAULT_RESULT_IMAGE_MAX_BYTES
        )
    )
    skin_metrics_baseline: Optional[dict[str, Any]] = field(
        default_factory=lambda: _env_optional_json(
            "MVP_SKIN_METRICS_BASELINE", DEFAULT_SKIN_METRICS_BASELINE
        )
    )
    plan_capability_baseline: Optional[dict[str, Any]] = field(
        default_factory=lambda: _env_optional_json(
            "MVP_PLAN_CAPABILITY_BASELINE", DEFAULT_PLAN_CAPABILITY_BASELINE
        )
    )
    plan_capability_stale_seconds: int = field(
        default_factory=lambda: _env_int(
            "MVP_PLAN_CAPABILITY_STALE_SECONDS", DEFAULT_PLAN_CAPABILITY_STALE_SECONDS
        )
    )
    plan_wait_check_seconds: int = field(
        default_factory=lambda: _env_int(
            "MVP_PLAN_WAIT_CHECK_SECONDS", DEFAULT_PLAN_WAIT_CHECK_SECONDS
        )
    )
    plan_prompt_template_version: str = field(
        default_factory=lambda: _env(
            "MVP_D_PLAN_PROMPT_VERSION", DEFAULT_PROMPT_TEMPLATE_VERSION
        )
    )
    # --- 测试替身注入（默认=当前行为；仅 double 分支读取；生产由守卫 fail-closed） ---
    face_double_quality: str = field(
        default_factory=lambda: _env("MVP_D_FACE_DOUBLE_QUALITY", DEFAULT_FACE_DOUBLE_QUALITY)
    )
    face_double_required_views: tuple[str, ...] = field(
        default_factory=lambda: _env_list("MVP_D_FACE_DOUBLE_REQUIRED_VIEWS")
    )
    face_double_same_person: bool = field(
        default_factory=lambda: _env_bool("MVP_D_FACE_DOUBLE_SAME_PERSON", True)
    )
    face_double_search: str = field(
        default_factory=lambda: _env("MVP_D_FACE_DOUBLE_SEARCH", DEFAULT_FACE_DOUBLE_SEARCH)
    )
    plan_double_mode: str = field(
        default_factory=lambda: _env("MVP_D_PLAN_DOUBLE_MODE", DEFAULT_PLAN_DOUBLE_MODE)
    )
    # 进程级 hold：置 true 时测肤 analyze 以既有可重试异常失败 → job 保持在
    # queued（可释放，不 sleep/不改 DB）；用于 SC-02-09 旧分析完成时机控制。
    skin_double_hold: bool = field(
        default_factory=lambda: _env_bool("MVP_D_SKIN_DOUBLE_HOLD", DEFAULT_SKIN_DOUBLE_HOLD)
    )
    # --- 阿里云形状边界（真实激活需总协调授权凭据 + PoC，当前默认未激活） ---
    aliyun_activated: bool = field(
        default_factory=lambda: _env_bool("MVP_D_ALIYUN_ACTIVATED", False)
    )
    aliyun_endpoint: str = field(default_factory=lambda: os.environ.get("MVP_D_ALIYUN_ENDPOINT", ""))
    aliyun_access_key_id: str = field(
        default_factory=lambda: os.environ.get("MVP_D_ALIYUN_ACCESS_KEY_ID", "")
    )
    aliyun_access_key_secret: str = field(
        default_factory=lambda: os.environ.get("MVP_D_ALIYUN_ACCESS_KEY_SECRET", "")
    )
    aliyun_face_db_name: str = field(
        default_factory=lambda: os.environ.get("MVP_D_ALIYUN_FACE_DB_NAME", "")
    )
    aliyun_llm_model: str = field(
        default_factory=lambda: os.environ.get("MVP_D_ALIYUN_LLM_MODEL", "")
    )

    @classmethod
    def from_env(cls) -> "DConfig":
        return cls()

    def __post_init__(self) -> None:
        """非法注入取值在**加载期** fail fast（不接受静默回退）。"""
        if self.face_double_quality not in FACE_DOUBLE_QUALITY_MODES:
            raise ProviderConfigError(
                f"invalid MVP_D_FACE_DOUBLE_QUALITY={self.face_double_quality!r};"
                f" expected one of {FACE_DOUBLE_QUALITY_MODES}"
            )
        if self.face_double_search not in FACE_DOUBLE_SEARCH_MODES:
            raise ProviderConfigError(
                f"invalid MVP_D_FACE_DOUBLE_SEARCH={self.face_double_search!r};"
                f" expected one of {FACE_DOUBLE_SEARCH_MODES}"
            )
        if self.plan_double_mode not in PLAN_DOUBLE_MODES:
            raise ProviderConfigError(
                f"invalid MVP_D_PLAN_DOUBLE_MODE={self.plan_double_mode!r};"
                f" expected one of {PLAN_DOUBLE_MODES}"
            )
        unknown_views = [
            view for view in self.face_double_required_views if view not in REQUIRED_VIEWS_ALL
        ]
        if unknown_views:
            raise ProviderConfigError(
                f"invalid MVP_D_FACE_DOUBLE_REQUIRED_VIEWS={list(unknown_views)!r};"
                f" allowed views are {list(REQUIRED_VIEWS_ALL)}"
            )

    # --- 基线访问器（结构性读取，缺失返回 None） ---
    def metric_baseline_by_name(self) -> dict[str, dict[str, Any]]:
        baseline = self.skin_metrics_baseline or {}
        out: dict[str, dict[str, Any]] = {}
        for m in baseline.get("metrics", []) or []:
            if isinstance(m, dict) and isinstance(m.get("name"), str):
                out[m["name"]] = m
        return out
