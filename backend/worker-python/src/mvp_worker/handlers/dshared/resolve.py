"""端口/存储/配置解析：测试经 ``HandlerContext.extras`` 注入，生产按 env 工厂。

``extras`` 键：``face_port`` / ``skin_port`` / ``plan_port`` / ``storage`` / ``dconfig``。
未注入时按 :class:`DConfig` + ``WorkerConfig.environment`` 构建；生产环境解析到替身或
阿里云适配器未激活 → 映射为可重试 ``DEPENDENCY_UNAVAILABLE``（fail-closed）。
``storage`` 改为按 ``MVP_D_STORAGE_PROVIDER`` 选择（``double``/``aliyun_oss``）；
``aliyun_oss`` 缺配置或生产 + ``double`` → :class:`ProviderConfigError`，**绝不**静默
回退本地文件系统。
"""
from __future__ import annotations

from typing import Any

from .. import HandlerContext, JobFailed
from .dconfig import DConfig
from .providers import (
    build_face_port,
    build_plan_port,
    build_skin_port,
    build_storage_port,
    ProviderConfigError,
    ProviderNotActivated,
    ProviderUnavailable,
)


def dconfig_for(ctx: HandlerContext) -> DConfig:
    injected = ctx.extras.get("dconfig")
    if injected is not None:
        return injected
    return DConfig.from_env()


def _dependency_failed(kind: str, exc: Exception) -> JobFailed:
    return JobFailed(
        "DEPENDENCY_UNAVAILABLE",
        f"{kind} provider unavailable ({type(exc).__name__})",
        retryable=True,
    )


def face_port_for(ctx: HandlerContext) -> Any:
    injected = ctx.extras.get("face_port")
    if injected is not None:
        return injected
    try:
        return build_face_port(dconfig_for(ctx), environment=ctx.config.environment)
    except (ProviderConfigError, ProviderNotActivated, ProviderUnavailable) as exc:
        raise _dependency_failed("face", exc) from exc


def skin_port_for(ctx: HandlerContext) -> Any:
    """皮肤 provider 解析：**不吞** :class:`ProviderConfigError`（镜像 ``plan_port_for``）。

    shuiguang 缺 BASE_URL/INPUT_ROOT、未知 provider、生产 + double 拒绝 → 由 handler
    落**终态** ``SKIN_PROVIDER_CONFIG``（fenced，1 次不重试，避免 retry storm 与 T05
    滞留）；``ProviderNotActivated``/``ProviderUnavailable`` 保持可重试
    ``DEPENDENCY_UNAVAILABLE``。face/storage 解析路径**不变**。
    """
    injected = ctx.extras.get("skin_port")
    if injected is not None:
        return injected
    try:
        return build_skin_port(dconfig_for(ctx), environment=ctx.config.environment)
    except (ProviderNotActivated, ProviderUnavailable) as exc:
        raise _dependency_failed("skin", exc) from exc


def plan_port_for(ctx: HandlerContext) -> Any:
    """计划 provider 解析：**不吞** :class:`ProviderConfigError`。

    计划 provider 的配置错误（llm_rag 缺 BASE_URL/API_KEY、生产 double 拒绝、未知
    provider）必须由 ``plan_generate`` 落**终态** ``PLAN_PROVIDER_CONFIG``（fenced，
    T06 与 T12 原子 failed），而非此处的可重试 ``DEPENDENCY_UNAVAILABLE``（避免 retry
    storm 与 T06 滞留）。face/skin/storage 解析路径**不变**。
    """
    injected = ctx.extras.get("plan_port")
    if injected is not None:
        return injected
    return build_plan_port(dconfig_for(ctx), environment=ctx.config.environment)


def storage_for(ctx: HandlerContext) -> Any:
    """按 ``MVP_D_STORAGE_PROVIDER`` 选择存储端口（**绝不**静默回退文件系统）。

    未注入时构建；``aliyun_oss`` 缺 bucket/AK/SK → :class:`ProviderConfigError`
    （消息只含键名，不含取值）；生产 + ``double`` → :class:`ProviderConfigError`。
    """
    injected = ctx.extras.get("storage")
    if injected is not None:
        return injected
    return build_storage_port(
        dconfig_for(ctx),
        environment=ctx.config.environment,
        dev_dir=ctx.config.storage_dev_dir,
    )
