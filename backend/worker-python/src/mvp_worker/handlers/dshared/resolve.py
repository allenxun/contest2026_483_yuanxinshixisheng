"""端口/存储/配置解析：测试经 ``HandlerContext.extras`` 注入，生产按 env 工厂。

``extras`` 键：``face_port`` / ``skin_port`` / ``plan_port`` / ``storage`` / ``dconfig``。
未注入时按 :class:`DConfig` + ``WorkerConfig.environment`` 构建；生产环境解析到替身或
阿里云适配器未激活 → 映射为可重试 ``DEPENDENCY_UNAVAILABLE``（fail-closed）。
"""
from __future__ import annotations

from typing import Any

from .. import HandlerContext, JobFailed
from ...media.storage import FilesystemStorageDouble
from .dconfig import DConfig
from .providers import (
    build_face_port,
    build_plan_port,
    build_skin_port,
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
    injected = ctx.extras.get("skin_port")
    if injected is not None:
        return injected
    try:
        return build_skin_port(dconfig_for(ctx), environment=ctx.config.environment)
    except (ProviderConfigError, ProviderNotActivated, ProviderUnavailable) as exc:
        raise _dependency_failed("skin", exc) from exc


def plan_port_for(ctx: HandlerContext) -> Any:
    injected = ctx.extras.get("plan_port")
    if injected is not None:
        return injected
    try:
        return build_plan_port(dconfig_for(ctx), environment=ctx.config.environment)
    except (ProviderConfigError, ProviderNotActivated, ProviderUnavailable) as exc:
        raise _dependency_failed("plan", exc) from exc


def storage_for(ctx: HandlerContext) -> Any:
    injected = ctx.extras.get("storage")
    if injected is not None:
        return injected
    return FilesystemStorageDouble(ctx.config.storage_dev_dir)
