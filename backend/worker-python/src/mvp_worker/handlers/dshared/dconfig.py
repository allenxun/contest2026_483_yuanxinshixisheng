"""D 包 env 配置与受控基线（MVP 明确标注为占位/待设备团队批准）。

env 一览（全部可选，dev 初值仅为联调起点，非验收硬值）：

| env | 默认 | 说明 |
|---|---|---|
| ``MVP_D_FACE_PROVIDER`` | ``double`` | double / aliyun_face / insightface |
| ``MVP_D_SKIN_PROVIDER`` | ``double`` | double / aliyun_skin / shuiguang |
| ``MVP_D_PLAN_PROVIDER`` | ``double`` | double / aliyun_llm / llm_rag |
| ``MVP_D_STORAGE_PROVIDER`` | ``double`` | double / aliyun_oss（生产 double → 拒绝） |
| ``MVP_A_STORAGE_OSS_REGION`` | ``cn-hangzhou`` | OSS 区域（对齐 Java app.storage.oss.region） |
| ``MVP_A_STORAGE_OSS_SERVER_ENDPOINT`` | 未设（aliyun_oss 必填） | 服务端访问 endpoint，对象操作用（对齐 Java app.storage.oss.server-endpoint） |
| ``MVP_A_STORAGE_OSS_PUBLIC_ENDPOINT`` | 未设（aliyun_oss 必填） | 客户端公网 endpoint，签名地址用（对齐 Java app.storage.oss.public-endpoint） |
| ``MVP_A_STORAGE_OSS_BUCKET`` | 未设（aliyun_oss 必填） | OSS 私有桶名（对齐 Java app.storage.oss.bucket） |
| ``MVP_A_STORAGE_OSS_ACCESS_KEY_ID`` | 未设（aliyun_oss 必填） | OSS AK（只走 env，绝不入仓） |
| ``MVP_A_STORAGE_OSS_ACCESS_KEY_SECRET`` | 未设（aliyun_oss 必填） | OSS SK（只走 env，绝不入仓） |
| ``MVP_A_STORAGE_OSS_SECURITY_TOKEN`` | 未设 | 可选 STS token（提供时用 V4 签名） |
| ``MVP_IDENTITY_NAMESPACE`` | ``mvp-ns-1`` | 人脸库命名空间 |
| ``MVP_D_PROVIDER_CONFIG_REVISION`` | ``1`` | 供应商配置代次（对账用） |
| ``MVP_D_RESULT_IMAGE_MAX_BYTES`` | ``10485760`` | 结果图大小上限（10MiB） |
| ``MVP_SKIN_METRICS_BASELINE`` | 内置受控基线 | JSON；指标白名单（name/unit/min/max） |
| ``MVP_D_SHUIGUANG_BASE_URL`` | （无，必填） | 真实 shuiguang 服务基址；provider=shuiguang 时必填 |
| ``MVP_D_SHUIGUANG_INPUT_ROOT`` | （无，必填） | 共享挂载输入根；provider=shuiguang 时必须为可写目录 |
| ``MVP_D_SHUIGUANG_CONNECT_TIMEOUT_MS`` | ``2000`` | 严格整数 ≥1 |
| ``MVP_D_SHUIGUANG_READ_TIMEOUT_MS`` | ``10000`` | 严格整数 ≥1 |
| ``MVP_D_SHUIGUANG_POLL_INTERVAL_SECONDS`` | ``2`` | 轮询间隔秒（严格整数 ≥1） |
| ``MVP_D_SHUIGUANG_POLL_MAX_SECONDS`` | ``120`` | 轮询总预算秒（严格整数 ≥1） |
| ``MVP_PLAN_CAPABILITY_BASELINE`` | 内置受控基线 | JSON；能力/参数范围/批准区域/N 边界 |
| ``MVP_PLAN_CAPABILITY_STALE_SECONDS`` | ``86400`` | T04 观察新鲜窗口；0=忽略 |
| ``MVP_PLAN_WAIT_CHECK_SECONDS`` | ``30`` | 能力待补齐的 defer 再检查间隔（合法等待态，不消耗 attempt） |
| ``MVP_D_PLAN_PROMPT_VERSION`` | ``1`` | 方案提示模板版本 |
| ``MVP_D_LLM_RAG_BASE_URL`` | 未设（llm_rag 必填） | weijing assess Base URL（只走 env，绝不入仓） |
| ``MVP_D_LLM_RAG_API_KEY`` | 未设（llm_rag 必填） | X-API-Key（只走 env，绝不入仓、绝不日志） |
| ``MVP_D_LLM_RAG_TIMEOUT_SECONDS`` | ``30`` | HTTP 超时（严格整数 >=1） |
| ``MVP_D_LLM_RAG_REQUEST_MAPPING`` | 未设 | 批准钩子：请求映射 JSON（未设=未批准，fail-closed） |
| ``MVP_D_LLM_RAG_OUTPUT_MAPPING`` | 未设 | 批准钩子：输出映射 JSON（未设=未批准，fail-closed） |
| ``MVP_D_FACE_DOUBLE_QUALITY`` | ``accepted`` | 测试注入：face 质量（``accepted``/``needs_retake``；后者可配 required views） |
| ``MVP_D_FACE_DOUBLE_REQUIRED_VIEWS`` | 空 | 测试注入：逗号分隔补拍视角（仅 ``front``/``left``/``right`` 子集；空=替身默认；全空段如 ``",,,"`` → 加载期 fail fast） |
| ``MVP_D_FACE_DOUBLE_SAME_PERSON`` | ``true`` | 测试注入：同人判定（严格布尔 ``1/true/yes/on`` 或 ``0/false/no/off``；``false`` → NOT_SAME_PERSON） |
| ``MVP_D_FACE_DOUBLE_SEARCH`` | ``reliable_new`` | 测试注入：1:N 分类（``reliable_new``/``matched``/``uncertain``/``ambiguous``/``dependency_failed``） |
| ``MVP_D_SKIN_DOUBLE_HOLD`` | ``false`` | 测试注入：进程级 hold（严格布尔；analyze 可重试失败，旧执行停在 queued，可释放） |
| ``MVP_D_SKIN_DOUBLE_INVALID`` | ``none`` | 测试注入：skin 指标违约（``none``/``unknown_metric``/``out_of_range``/``bad_unit``）→ 既有 ``PROVIDER_CONTRACT_VIOLATION`` 终态 |
| ``MVP_D_SKIN_V3_MOCK`` | ``false`` | 测试注入：dev/test 下 skin 替身携带 V3 三组 mock（严格布尔；生产信号 + true → 拒绝启动） |
| ``MVP_D_DOUBLE_LATE_BARRIER`` | ``false`` | 测试注入：SC-02-09 迟到返回 barrier（严格布尔；一次性/有界；仅 face 首个调用） |
| ``MVP_D_DOUBLE_LATE_BARRIER_DIR`` | 空 | barrier 文件目录（**barrier=true 时必填**，须每 RUN_ID 独立；空→加载期 fail fast；释放=写 ``released``） |
| ``MVP_D_DOUBLE_LATE_BARRIER_SHA256`` | 空 | 命中标记：被拦照片内容的 sha256（64 hex），barrier 开启时必填 |
| ``MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS`` | ``30`` | barrier 等待上限（整数 >=1；非数字/越界→加载期 fail fast；超时清理并抛 ProviderUnavailable） |
| ``MVP_D_PLAN_DOUBLE_MODE`` | ``valid`` | 测试注入：``valid``/``timeout``/``failure`` 或 PlanDouble 既有非法形状名 |
| ``MVP_D_STORAGE_DOUBLE_FAIL_PUT`` | ``false`` | 测试注入：``assessment_result`` 用途 put 受控失败（严格布尔；可重试 RESULT_ARCHIVE_FAILED） |
| ``MVP_D_ALIYUN_ACTIVATED`` | ``false`` | 阿里云适配器真实激活开关（需凭据 + PoC） |
| ``MVP_D_ALIYUN_ENDPOINT`` / ``_ACCESS_KEY_ID`` / ``_ACCESS_KEY_SECRET`` | 未设 | 阿里云凭据（只走 env，绝不入仓） |
| ``MVP_D_ALIYUN_FACE_DB_NAME`` / ``MVP_D_ALIYUN_LLM_MODEL`` | 未设 | 人脸库 DbName / 大模型名 |
| ``MVP_D_FACE_SERVICE_BASE_URL`` | 未设（insightface 必填） | face-service Base URL（只走 env，绝不入仓） |
| ``MVP_D_FACE_SERVICE_NAMESPACE`` | 未设（insightface 必填） | face-service 命名空间（insightface 必填） |
| ``MVP_D_FACE_SERVICE_TOKEN_FILE`` | 未设（insightface 必填） | 内部 token 文件路径（**仅从权限 0600 的普通文件读取**；绝不入仓、绝不日志/回显） |
| ``MVP_D_FACE_SERVICE_CONNECT_TIMEOUT_MS`` | ``2000`` | face-service 连接超时（严格整数 >=1） |
| ``MVP_D_FACE_SERVICE_READ_TIMEOUT_MS`` | ``35000`` | face-service 读超时（严格整数 >=1；**>= 服务端推理超时 30s**，见合同 §7） |
| ``MVP_D_FACE_SERVICE_AUTO_ENROLL`` | ``false`` | 自动登记门（严格布尔；**默认关闭**=未过 PoC/未标定/无活体，register 零网络拒绝；见合同 §4.2 裁定 2） |

**基线是 MVP 受控占位**：真实设备协议/指标口径待设备团队批准；代码只信任这里
列出的白名单，绝不发布未批准指标/区域/参数。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from typing import Any, Optional

from ...media.storage import (
    DEFAULT_OSS_REGION,
    OSS_ACCESS_KEY_ID_ENV,
    OSS_ACCESS_KEY_SECRET_ENV,
    OSS_BUCKET_ENV,
    OSS_PUBLIC_ENDPOINT_ENV,
    OSS_REGION_ENV,
    OSS_SECURITY_TOKEN_ENV,
    OSS_SERVER_ENDPOINT_ENV,
    STORAGE_DOUBLE_FAIL_PUT_ENV,
    STORAGE_PROVIDER_ALIYUN_OSS,
    STORAGE_PROVIDER_DOUBLE,
    STORAGE_PROVIDER_ENV,
    STORAGE_PROVIDERS,
)
from .constants import REQUIRED_VIEWS_ALL


class ProviderConfigError(RuntimeError):
    """配置错误（生产解析到替身 / 非法注入取值 / 生产出现注入开关）。

    定义在配置模块以避免 ``providers`` 的循环依赖；``providers`` 重新导出同名符号，
    既有 ``from ...providers import ProviderConfigError`` 保持可用。
    """


DEFAULT_FACE_PROVIDER = "double"
DEFAULT_SKIN_PROVIDER = "double"

#: 真实 shuiguang 适配器配置（provider=shuiguang 时 BASE_URL/INPUT_ROOT 必填，否则
#: 端口构造期 fail-closed ``ProviderConfigError``——绝不部分激活）。
SHUIGUANG_BASE_URL_ENV = "MVP_D_SHUIGUANG_BASE_URL"
SHUIGUANG_INPUT_ROOT_ENV = "MVP_D_SHUIGUANG_INPUT_ROOT"
DEFAULT_SHUIGUANG_CONNECT_TIMEOUT_MS = 2000
DEFAULT_SHUIGUANG_READ_TIMEOUT_MS = 10000
DEFAULT_SHUIGUANG_POLL_INTERVAL_SECONDS = 2
DEFAULT_SHUIGUANG_POLL_MAX_SECONDS = 120
DEFAULT_PLAN_PROVIDER = "double"
DEFAULT_STORAGE_PROVIDER = STORAGE_PROVIDER_DOUBLE
DEFAULT_IDENTITY_NAMESPACE = "mvp-ns-1"
DEFAULT_PROVIDER_CONFIG_REVISION = "1"
DEFAULT_RESULT_IMAGE_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_PLAN_CAPABILITY_STALE_SECONDS = 86400
DEFAULT_PLAN_WAIT_CHECK_SECONDS = 30
DEFAULT_PROMPT_TEMPLATE_VERSION = "1"
DEFAULT_LLM_RAG_TIMEOUT_SECONDS = 30

# --- insightface / face-service HTTP 绑定（phase 2：真实绑定冻结合同） ---
#: 允许的 face provider（含 ``insightface``；未知值仍在工厂 fail fast）。
FACE_PROVIDERS = ("double", "aliyun_face", "insightface")
DEFAULT_FACE_SERVICE_CONNECT_TIMEOUT_MS = 2000
#: 读超时必须 **>= 服务端推理超时**（``FACE_SVC_INFERENCE_TIMEOUT_SECONDS`` 默认 30s），
#: 否则客户端会在服务端仍在推理时误判 timeout（合同 §7）。取 35s 留有余量。
DEFAULT_FACE_SERVICE_READ_TIMEOUT_MS = 35000
#: 自动登记门默认关闭：PoC / 阈值标定 / 活体条件未验证前**不得**真实自动登记
#: （合同 §4.2 裁定 2；``后端详细设计-V1-MVP.md:663``）。register 在关闭时零网络拒绝。
DEFAULT_FACE_SERVICE_AUTO_ENROLL = False

#: face-service 绑定 env 键（集中登记；错误消息只报键名/路径，绝不回显取值）。
FACE_SERVICE_BASE_URL_ENV = "MVP_D_FACE_SERVICE_BASE_URL"
FACE_SERVICE_NAMESPACE_ENV = "MVP_D_FACE_SERVICE_NAMESPACE"
FACE_SERVICE_TOKEN_FILE_ENV = "MVP_D_FACE_SERVICE_TOKEN_FILE"
FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV = "MVP_D_FACE_SERVICE_CONNECT_TIMEOUT_MS"
FACE_SERVICE_READ_TIMEOUT_MS_ENV = "MVP_D_FACE_SERVICE_READ_TIMEOUT_MS"
FACE_SERVICE_AUTO_ENROLL_ENV = "MVP_D_FACE_SERVICE_AUTO_ENROLL"

# --- 测试替身注入（默认值 = 当前行为 = 不注入；仅读 double 分支，生产 fail-closed） ---
DEFAULT_FACE_DOUBLE_QUALITY = "accepted"
DEFAULT_FACE_DOUBLE_SEARCH = "reliable_new"
DEFAULT_PLAN_DOUBLE_MODE = "valid"
DEFAULT_SKIN_DOUBLE_HOLD = False
DEFAULT_SKIN_DOUBLE_INVALID = "none"
DEFAULT_SKIN_V3_MOCK = False

#: V3 三组 mock 开关（仅 dev/test；生产信号 + true → fail-closed 拒绝启动）。
SKIN_V3_MOCK_ENV = "MVP_D_SKIN_V3_MOCK"
DEFAULT_DOUBLE_LATE_BARRIER = False
DEFAULT_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS = 30

#: SC-02-09 迟到返回 barrier 的 env 名（一次性、文件态、有界；默认关闭）。
DOUBLE_LATE_BARRIER_DIR_ENV = "MVP_D_DOUBLE_LATE_BARRIER_DIR"
DOUBLE_LATE_BARRIER_SHA256_ENV = "MVP_D_DOUBLE_LATE_BARRIER_SHA256"
DOUBLE_LATE_BARRIER_TIMEOUT_ENV = "MVP_D_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS"

# SkinDouble._apply_invalid 的既有非法形状名（与 providers.SkinDouble 一一对应）。
SKIN_DOUBLE_INVALID_MODES = ("none", "unknown_metric", "out_of_range", "bad_unit")

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
    "MVP_D_SKIN_DOUBLE_INVALID": DEFAULT_SKIN_DOUBLE_INVALID,
    SKIN_V3_MOCK_ENV: DEFAULT_SKIN_V3_MOCK,
    "MVP_D_DOUBLE_LATE_BARRIER": DEFAULT_DOUBLE_LATE_BARRIER,
    DOUBLE_LATE_BARRIER_DIR_ENV: "",
    DOUBLE_LATE_BARRIER_SHA256_ENV: "",
    DOUBLE_LATE_BARRIER_TIMEOUT_ENV: str(DEFAULT_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS),
    STORAGE_DOUBLE_FAIL_PUT_ENV: False,
}
_BOOLEAN_INJECTION_SWITCHES = frozenset(
    {
        "MVP_D_FACE_DOUBLE_SAME_PERSON",
        "MVP_D_SKIN_DOUBLE_HOLD",
        "MVP_D_DOUBLE_LATE_BARRIER",
        STORAGE_DOUBLE_FAIL_PUT_ENV,
        SKIN_V3_MOCK_ENV,
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


def _strict_env_int(name: str, default: int, *, minimum: int) -> int:
    """注入开关专用严格整数解析：非数字 / 低于下界 → 加载期 ``ProviderConfigError``。

    与既有 ``_env_int``（裸 ``ValueError``、仅内部旋钮）区分：本函数统一异常类型并
    在消息中给出变量名与取值域，保证 DB/端口启动前 fail fast。
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ProviderConfigError(
            f"invalid {name}={raw!r}; expected integer >= {minimum}"
        ) from None
    if value < minimum:
        raise ProviderConfigError(
            f"invalid {name}={raw!r}; expected integer >= {minimum}"
        )
    return value


def _env_bool(name: str, default: bool) -> bool:
    """既有非注入旋钮的宽松布尔解析（**保持不变**；未知值静默按 False）。"""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


#: 注入开关专用严格布尔值域（仅显式真/假；其余任何值 → 加载期 fail fast）。
BOOL_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
BOOL_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
BOOL_ENV_DOMAIN = "1/true/yes/on | 0/false/no/off"


def strict_env_bool(name: str, default: bool) -> bool:
    """**注入开关专用**严格布尔解析（唯一语义，守卫与运行时共用）。

    - 未设 / 空（trim 后）→ ``default``；
    - ``1/true/yes/on``（忽略大小写与首尾空白）→ True；
    - ``0/false/no/off`` → False；
    - 其它任何值 → :class:`ProviderConfigError`（消息含变量名、实际取值、允许值域）。

    与 :func:`_env_bool` 不同：绝不把未知值静默当 False，避免"注入开关被误配却
    悄悄生效/失效"。
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    normalized = raw.lower()
    if normalized in BOOL_TRUE_VALUES:
        return True
    if normalized in BOOL_FALSE_VALUES:
        return False
    raise ProviderConfigError(
        f"invalid boolean for {name}={raw!r}; allowed values: {BOOL_ENV_DOMAIN}"
        f" (or unset/empty → {default})"
    )


def _env_list(name: str) -> tuple[str, ...]:
    """逗号分隔清单；缺省/空 → ()（= 使用替身自身默认）。

    非空但**全为空段**（如 ``",,,"``）→ 加载期 fail fast，不静默回退默认。
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return ()
    parts = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not parts:
        raise ProviderConfigError(
            f"invalid list for {name}={raw!r}; expected comma-separated non-empty values"
        )
    return parts


def double_injection_overrides() -> dict[str, str]:
    """返回被**显式设为非默认语义值**的注入开关（缺失/默认值不算）。

    布尔开关复用 :func:`strict_env_bool`（与 DConfig / 运行时读取**同一语义**）：
    合法值按语义比较（``0/no/off`` 与默认 false 等价），**非法值直接抛
    :class:`ProviderConfigError`**（守卫路径明确报错，不按 False 比较后放过）。
    """
    overrides: dict[str, str] = {}
    for name, default in DOUBLE_INJECTION_SWITCHES.items():
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        if name in _BOOLEAN_INJECTION_SWITCHES:
            value = strict_env_bool(name, bool(default))  # 非法值 → 明确报错
            if value != bool(default):
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


@dataclass(frozen=True, repr=False)
class DConfig:
    face_provider: str = field(
        default_factory=lambda: _env("MVP_D_FACE_PROVIDER", DEFAULT_FACE_PROVIDER)
    )
    skin_provider: str = field(
        default_factory=lambda: _env("MVP_D_SKIN_PROVIDER", DEFAULT_SKIN_PROVIDER)
    )
    # --- 真实 shuiguang skin provider（provider=shuiguang 时 BASE_URL/INPUT_ROOT 必填） ---
    shuiguang_base_url: str = field(
        default_factory=lambda: _env(SHUIGUANG_BASE_URL_ENV, "")
    )
    shuiguang_input_root: str = field(
        default_factory=lambda: _env(SHUIGUANG_INPUT_ROOT_ENV, "")
    )
    shuiguang_connect_timeout_ms: int = field(
        default_factory=lambda: _strict_env_int(
            "MVP_D_SHUIGUANG_CONNECT_TIMEOUT_MS",
            DEFAULT_SHUIGUANG_CONNECT_TIMEOUT_MS,
            minimum=1,
        )
    )
    shuiguang_read_timeout_ms: int = field(
        default_factory=lambda: _strict_env_int(
            "MVP_D_SHUIGUANG_READ_TIMEOUT_MS",
            DEFAULT_SHUIGUANG_READ_TIMEOUT_MS,
            minimum=1,
        )
    )
    shuiguang_poll_interval_seconds: int = field(
        default_factory=lambda: _strict_env_int(
            "MVP_D_SHUIGUANG_POLL_INTERVAL_SECONDS",
            DEFAULT_SHUIGUANG_POLL_INTERVAL_SECONDS,
            minimum=1,
        )
    )
    shuiguang_poll_max_seconds: int = field(
        default_factory=lambda: _strict_env_int(
            "MVP_D_SHUIGUANG_POLL_MAX_SECONDS",
            DEFAULT_SHUIGUANG_POLL_MAX_SECONDS,
            minimum=1,
        )
    )
    plan_provider: str = field(
        default_factory=lambda: _env("MVP_D_PLAN_PROVIDER", DEFAULT_PLAN_PROVIDER)
    )
    # --- 存储 provider（按服务独立选择；生产 double → fail-closed） ---
    storage_provider: str = field(
        default_factory=lambda: _env(STORAGE_PROVIDER_ENV, DEFAULT_STORAGE_PROVIDER)
    )
    oss_region: str = field(
        default_factory=lambda: _env(OSS_REGION_ENV, DEFAULT_OSS_REGION)
    )
    # 两个 endpoint 均无默认：aliyun_oss 模式下缺失 → 构建期 ProviderConfigError。
    # endpoint 亦按敏感配置处理，错误消息只含键名、绝不回显取值。
    oss_server_endpoint: str = field(
        default_factory=lambda: os.environ.get(OSS_SERVER_ENDPOINT_ENV, "")
    )
    oss_public_endpoint: str = field(
        default_factory=lambda: os.environ.get(OSS_PUBLIC_ENDPOINT_ENV, "")
    )
    # bucket/AK/SK 无默认：aliyun_oss 模式下缺失 → 构建期 ProviderConfigError（只报键名）。
    oss_bucket: str = field(default_factory=lambda: os.environ.get(OSS_BUCKET_ENV, ""))
    oss_access_key_id: str = field(
        default_factory=lambda: os.environ.get(OSS_ACCESS_KEY_ID_ENV, "")
    )
    oss_access_key_secret: str = field(
        default_factory=lambda: os.environ.get(OSS_ACCESS_KEY_SECRET_ENV, "")
    )
    oss_security_token: str = field(
        default_factory=lambda: os.environ.get(OSS_SECURITY_TOKEN_ENV, "")
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
    # --- llm_rag 真实 AI 方案 provider（weijing assess；缺配置 → 构建期 ProviderConfigError） ---
    llm_rag_base_url: str = field(
        default_factory=lambda: os.environ.get("MVP_D_LLM_RAG_BASE_URL", "")
    )
    llm_rag_api_key: str = field(
        default_factory=lambda: os.environ.get("MVP_D_LLM_RAG_API_KEY", "")
    )
    llm_rag_timeout_seconds: int = field(
        default_factory=lambda: _strict_env_int(
            "MVP_D_LLM_RAG_TIMEOUT_SECONDS", DEFAULT_LLM_RAG_TIMEOUT_SECONDS, minimum=1
        )
    )
    # 批准钩子：JSON 配置激活**已注册**映射；未设 = 未批准（fail-closed）。
    llm_rag_request_mapping: Optional[dict[str, Any]] = field(
        default_factory=lambda: _env_optional_json("MVP_D_LLM_RAG_REQUEST_MAPPING", None)
    )
    llm_rag_output_mapping: Optional[dict[str, Any]] = field(
        default_factory=lambda: _env_optional_json("MVP_D_LLM_RAG_OUTPUT_MAPPING", None)
    )
    # --- 测试替身注入（默认=当前行为；仅 double 分支读取；生产由守卫 fail-closed） ---
    face_double_quality: str = field(
        default_factory=lambda: _env("MVP_D_FACE_DOUBLE_QUALITY", DEFAULT_FACE_DOUBLE_QUALITY)
    )
    face_double_required_views: tuple[str, ...] = field(
        default_factory=lambda: _env_list("MVP_D_FACE_DOUBLE_REQUIRED_VIEWS")
    )
    # 布尔注入开关三者均用严格解析（未知值加载期 fail fast；既有 _env_bool 不动）。
    face_double_same_person: bool = field(
        default_factory=lambda: strict_env_bool("MVP_D_FACE_DOUBLE_SAME_PERSON", True)
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
        default_factory=lambda: strict_env_bool("MVP_D_SKIN_DOUBLE_HOLD", DEFAULT_SKIN_DOUBLE_HOLD)
    )
    # 存储注入开关：严格校验纳入 DConfig，使 __main__ 启动校验路径可见；
    # storage.storage_put_failure_injected() 复用同一 strict_env_bool（单一语义）。
    storage_double_fail_put: bool = field(
        default_factory=lambda: strict_env_bool(STORAGE_DOUBLE_FAIL_PUT_ENV, False)
    )
    # SC-02-10：skin 替身返回违反既有白名单/基线的指标 → 既有 PROVIDER_CONTRACT_VIOLATION 终态。
    skin_double_invalid: str = field(
        default_factory=lambda: _env("MVP_D_SKIN_DOUBLE_INVALID", DEFAULT_SKIN_DOUBLE_INVALID)
    )
    # V3 三组 mock 开关（严格布尔；默认关闭）。生产信号 + true → 既有生产守卫拒绝启动。
    skin_v3_mock: bool = field(
        default_factory=lambda: strict_env_bool(SKIN_V3_MOCK_ENV, DEFAULT_SKIN_V3_MOCK)
    )
    # SC-02-09：文件式一次性 barrier（先算后等/有界/默认关闭），仅 FaceDouble 首个调用读取。
    double_late_barrier: bool = field(
        default_factory=lambda: strict_env_bool(
            "MVP_D_DOUBLE_LATE_BARRIER", DEFAULT_DOUBLE_LATE_BARRIER
        )
    )
    double_late_barrier_dir: str = field(
        default_factory=lambda: _env(DOUBLE_LATE_BARRIER_DIR_ENV, "")
    )
    double_late_barrier_sha256: str = field(
        default_factory=lambda: _env(DOUBLE_LATE_BARRIER_SHA256_ENV, "")
    )
    double_late_barrier_timeout_seconds: int = field(
        default_factory=lambda: _strict_env_int(
            DOUBLE_LATE_BARRIER_TIMEOUT_ENV,
            DEFAULT_DOUBLE_LATE_BARRIER_TIMEOUT_SECONDS,
            minimum=1,
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
    # --- insightface / face-service HTTP 绑定（phase 2；密钥只从 0600 文件读） ---
    # Base URL / namespace / token 文件均无默认：insightface 模式下缺失 → 构建期
    # ProviderConfigError（消息只含键名/路径，绝不回显取值）。
    # **不含任何客户端阈值**：search/compare/quality 的阈值由服务端固定策略持有
    # （合同 §4.1/§5.1 明确禁止客户端阈值），phase 1 的 4 个阈值键已**移除**。
    face_service_base_url: str = field(
        default_factory=lambda: os.environ.get(FACE_SERVICE_BASE_URL_ENV, "")
    )
    face_service_namespace: str = field(
        default_factory=lambda: os.environ.get(FACE_SERVICE_NAMESPACE_ENV, "")
    )
    face_service_token_file: str = field(
        default_factory=lambda: os.environ.get(FACE_SERVICE_TOKEN_FILE_ENV, "")
    )
    face_service_connect_timeout_ms: int = field(
        default_factory=lambda: _strict_env_int(
            FACE_SERVICE_CONNECT_TIMEOUT_MS_ENV,
            DEFAULT_FACE_SERVICE_CONNECT_TIMEOUT_MS,
            minimum=1,
        )
    )
    face_service_read_timeout_ms: int = field(
        default_factory=lambda: _strict_env_int(
            FACE_SERVICE_READ_TIMEOUT_MS_ENV,
            DEFAULT_FACE_SERVICE_READ_TIMEOUT_MS,
            minimum=1,
        )
    )
    # 自动登记门：严格布尔；默认 false（register 零网络拒绝）。未知值加载期 fail fast。
    face_service_auto_enroll: bool = field(
        default_factory=lambda: strict_env_bool(
            FACE_SERVICE_AUTO_ENROLL_ENV, DEFAULT_FACE_SERVICE_AUTO_ENROLL
        )
    )

    @classmethod
    def from_env(cls) -> "DConfig":
        return cls()

    def __repr__(self) -> str:
        """脱敏 repr：**绝不**输出 AK/SK/STS token 与 endpoint/bucket 取值。

        dataclass 默认 repr 会把全部字段（含 ``oss_access_key_secret``、
        ``aliyun_access_key_secret``、``oss_security_token`` 以及两个 endpoint 与桶名）原样打印；
        一旦将来有人写 ``log.info("%s", cfg)`` 或把 cfg 带进异常消息就会泄漏凭据。
        这里按**字段名模式**脱敏，因此将来新增的同类字段会自动被覆盖，无需逐个登记；
        非敏感字段仍原样显示以便调试。当前全仓没有任何 ``repr(cfg)`` 调用路径
        （orchestrator 已 grep 核实：worker-python 的 src 与 tests 中 ``repr(`` 命中 0），
        故本方法属**预防性硬化**，不改变任何现有行为。
        """
        redact_hints = ("access_key", "secret", "token", "endpoint", "bucket")
        parts = [
            f"{f.name}='<redacted>'"
            if any(hint in f.name for hint in redact_hints)
            else f"{f.name}={getattr(self, f.name)!r}"
            for f in fields(self)
        ]
        return f"{type(self).__name__}({', '.join(parts)})"

    def __post_init__(self) -> None:
        """非法注入取值在**加载期** fail fast（不接受静默回退）。"""
        if self.storage_provider not in STORAGE_PROVIDERS:
            raise ProviderConfigError(
                f"invalid {STORAGE_PROVIDER_ENV}={self.storage_provider!r};"
                f" expected one of {STORAGE_PROVIDERS}"
            )
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
        if self.skin_double_invalid not in SKIN_DOUBLE_INVALID_MODES:
            raise ProviderConfigError(
                f"invalid MVP_D_SKIN_DOUBLE_INVALID={self.skin_double_invalid!r};"
                f" expected one of {SKIN_DOUBLE_INVALID_MODES}"
            )
        if self.double_late_barrier:
            if not self.double_late_barrier_dir.strip():
                raise ProviderConfigError(
                    f"invalid {DOUBLE_LATE_BARRIER_DIR_ENV}="
                    f"{self.double_late_barrier_dir!r}; barrier=true requires an explicit"
                    " dedicated directory (per-RUN_ID isolation; no shared default allowed)"
                )
            if self.double_late_barrier_timeout_seconds < 1:
                raise ProviderConfigError(
                    f"invalid {DOUBLE_LATE_BARRIER_TIMEOUT_ENV}="
                    f"{self.double_late_barrier_timeout_seconds!r}; expected integer >= 1"
                )
            marker = self.double_late_barrier_sha256.strip().lower()
            if len(marker) != 64 or any(c not in "0123456789abcdef" for c in marker):
                raise ProviderConfigError(
                    f"invalid {DOUBLE_LATE_BARRIER_SHA256_ENV}="
                    f"{self.double_late_barrier_sha256!r}; expected 64-char hex sha256"
                    " of the marked image (barrier enabled)"
                )

    # --- 基线访问器（结构性读取，缺失返回 None） ---
    def metric_baseline_by_name(self) -> dict[str, dict[str, Any]]:
        baseline = self.skin_metrics_baseline or {}
        out: dict[str, dict[str, Any]] = {}
        for m in baseline.get("metrics", []) or []:
            if isinstance(m, dict) and isinstance(m.get("name"), str):
                out[m["name"]] = m
        return out
