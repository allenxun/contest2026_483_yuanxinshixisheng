"""Handler 注册表 —— B/C/D 业务处理器的文档化扩展点。

扩展方式（详见 handlers/README.md）：
1. 在本目录新建 ``<job_type 规范化名>.py``，实现 :class:`Handler` 协议：
   - ``validate(payload)``：用 backend/contracts/schemas/payload-<job>.json 严格
     JSON Schema 校验；不认识/版本不符/违反 schema → 抛
     :class:`UnsupportedPayload`（运行时将标 failed/UNSUPPORTED_CONTRACT，不重试）。
   - ``handle(ctx, job)``：事务外做重活（算法/大模型/OSS 调用）；**每次外部
     调用间隙检查 ``ctx.abort_event``**（租约已丢 → 尽快返回，绝不提交结果）。
     需要写业务表时把"短事务回调"放进 :class:`HandlerResult` 的
     ``business_tx``：运行时在**同一个**最终事务里先执行它（先锁业务行）、
     再以代次守卫更新 async_jobs；守卫失败整体回滚（DD 8.1）。
     业务输入版本复核（如 processing_revision 仍是 job.input_revision）必须
     在 business_tx 内持锁后进行——这是"旧输入结果不发布"的落点。
2. 模块底部 ``register("<job_type>", Handler实例())``，并在本文件末尾的
   内置注册区 import 该模块。
3. 写入边界：只允许 async_jobs（本运行时管理）+ 本任务自己的 media_objects +
   设计中划给 Worker 的业务表字段（字段级 UPDATE，禁整行 upsert，禁写
   idempotency_requests）。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Protocol, runtime_checkable

from sqlalchemy import Connection
from sqlalchemy import Engine

from ..config import WorkerConfig
from ..runtime.complete import BusinessTx  # re-export：handler 返回值使用同一类型
from ..runtime.rows import JobRow


class UnsupportedPayload(ValueError):
    """payload 违反契约（未知 schema_version / JSON Schema 不通过）。"""


class JobFailed(RuntimeError):
    """handler 主动声明的任务失败。

    retryable=True → 运行按退避重排队（受 max_attempts 约束）；
    retryable=False（业务性/永久性失败）→ 直接 failed。
    """

    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass
class HandlerResult:
    """handle() 成功产物：可选业务写回调，由 complete_success 在同一事务执行。"""

    business_tx: Optional[BusinessTx] = None


@dataclass
class HandlerContext:
    engine: Engine
    config: WorkerConfig
    job: JobRow
    abort_event: threading.Event  # 租约丢失信号（协作式中止）
    extras: Dict[str, Any] = field(default_factory=dict)  # 如 storage port


@runtime_checkable
class Handler(Protocol):
    name: str

    def validate(self, payload: object) -> None: ...

    def handle(self, ctx: HandlerContext, job: JobRow) -> Optional[HandlerResult]: ...


_REGISTRY: Dict[str, Handler] = {}


def register(job_type: str, handler: Handler) -> None:
    if job_type in _REGISTRY:
        raise ValueError(f"handler already registered for job_type={job_type}")
    _REGISTRY[job_type] = handler


def get_handler(job_type: str) -> Optional[Handler]:
    return _REGISTRY.get(job_type)


def registered_job_types() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


# --- 内置注册（A 包仅 system.echo；业务类型见 handlers/README.md） ---
from . import system_echo as _system_echo  # noqa: E402

register(_system_echo.ECHO_JOB_TYPE, _system_echo.handler)

from . import notification_deliver as _notification_deliver  # noqa: E402

register(_notification_deliver.JOB_TYPE, _notification_deliver.handler)
