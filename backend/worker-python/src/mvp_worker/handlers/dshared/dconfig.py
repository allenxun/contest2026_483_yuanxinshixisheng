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

DEFAULT_FACE_PROVIDER = "double"
DEFAULT_SKIN_PROVIDER = "double"
DEFAULT_PLAN_PROVIDER = "double"
DEFAULT_IDENTITY_NAMESPACE = "mvp-ns-1"
DEFAULT_PROVIDER_CONFIG_REVISION = "1"
DEFAULT_RESULT_IMAGE_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_PLAN_CAPABILITY_STALE_SECONDS = 86400
DEFAULT_PLAN_WAIT_CHECK_SECONDS = 30
DEFAULT_PROMPT_TEMPLATE_VERSION = "1"

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

    # --- 基线访问器（结构性读取，缺失返回 None） ---
    def metric_baseline_by_name(self) -> dict[str, dict[str, Any]]:
        baseline = self.skin_metrics_baseline or {}
        out: dict[str, dict[str, Any]] = {}
        for m in baseline.get("metrics", []) or []:
            if isinstance(m, dict) and isinstance(m.get("name"), str):
                out[m["name"]] = m
        return out
