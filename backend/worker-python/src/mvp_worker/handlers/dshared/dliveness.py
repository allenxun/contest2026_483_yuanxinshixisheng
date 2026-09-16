"""活体（liveness）策略 —— 纯函数、可单测（phase 1 即可验证，无需 live service）。

事实基线（Worker 侧可依赖的**能力事实**，非 HTTP 合同细节）：face-service 的活体能力
恒定报告 ``{"supported": false, ...}``（所用模型没有活体检测），检测分数**绝不**作为
活体代理；显式要求活体的请求会被服务**诚实拒绝**而不是伪造结果。具体错误码/状态码属
于尚未冻结的合同面，本模块**不引用、不绑定**（见
``.mvp-d-runtime/waiting-dependency-insightface.md``）。

因此 Worker 侧策略必须：

1. **永不**请求 ``require_liveness=true``（适配器请求参数里根本不出现该键）；
2. 服务响应 ``liveness.supported=false`` **不构成失败**（不得中断身份链）；
3. **永不**产出“liveness passed”结论（只可能是 ``supported`` / ``unsupported``）。

本模块只有纯函数与常量，不 import providers，避免循环依赖。
"""
from __future__ import annotations

from typing import Any, Mapping

#: 适配器**永不**请求活体（显式常量，供测试与代码审查引用）。
ADAPTER_NEVER_REQUESTS_LIVENESS = True
#: 适配器绝不发送的请求键。
LIVENESS_REQUEST_PARAM = "require_liveness"
#: 服务侧恒定活体块里的支持标记键。
LIVENESS_SUPPORTED_KEY = "supported"
#: 结论枚举——注意**没有** "passed"。
LIVENESS_CONCLUSION_SUPPORTED = "supported"
LIVENESS_CONCLUSION_UNSUPPORTED = "unsupported"


def adapter_liveness_request_params() -> dict[str, Any]:
    """适配器可选的活体请求参数：恒为 ``{}``（永不显式要求活体）。

    返回**新字典**；任何调用方都无法通过修改返回值影响策略。
    """
    return {}


def liveness_is_supported(liveness: Mapping[str, Any] | None) -> bool:
    """仅当 ``liveness.supported is True`` 才视为支持（缺失/False/非映射=不支持）。"""
    if not isinstance(liveness, Mapping):
        return False
    return liveness.get(LIVENESS_SUPPORTED_KEY) is True


def liveness_supported_false_is_not_a_failure(liveness: Mapping[str, Any] | None) -> bool:
    """``supported=false``（或缺失/畸形）**不是失败** → 返回 True（不中断身份链）。

    该函数是对“活体不支持 ≠ 业务失败”这一策略的直接可单测编码：适配器不得因服务
    诚实报告 ``supported=false`` 而抛错或把身份链判失败。
    """
    return not liveness_is_supported(liveness)


def liveness_conclusion(liveness: Mapping[str, Any] | None) -> str:
    """返回 ``supported`` / ``unsupported``；**永不**返回 "passed"。"""
    return (
        LIVENESS_CONCLUSION_SUPPORTED
        if liveness_is_supported(liveness)
        else LIVENESS_CONCLUSION_UNSUPPORTED
    )


def liveness_never_concluded_passed(conclusion: str) -> bool:
    """守卫：结论字符串不得等于/包含 "passed"（大小写不敏感）。"""
    return "passed" not in str(conclusion).lower()


__all__ = [
    "ADAPTER_NEVER_REQUESTS_LIVENESS",
    "LIVENESS_REQUEST_PARAM",
    "LIVENESS_CONCLUSION_SUPPORTED",
    "LIVENESS_CONCLUSION_UNSUPPORTED",
    "adapter_liveness_request_params",
    "liveness_is_supported",
    "liveness_supported_false_is_not_a_failure",
    "liveness_conclusion",
    "liveness_never_concluded_passed",
]