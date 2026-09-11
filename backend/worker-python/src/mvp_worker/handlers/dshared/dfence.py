"""租约围栏的业务写事务：standalone 业务写必须先证明仍持有当前租约代次。

背景（oracle B1）：handler 内有些业务写在 ``complete_*`` 事务之外自开短事务
（状态标记、阶段持久化、终态标记）。这些写若只按 ``processing_revision``/
``status`` 守卫，那么**租约已过期被回收、新 owner 接管后**，旧 worker 仍可能提交
终态业务数据（如 T05 failed），污染新 owner 的任务；只有随后的 ``complete_failure``
被围栏丢弃，业务写却已落库。

本助手在**同一事务**内先 ``SELECT ... FOR UPDATE`` 锁住该 job 的 ``async_jobs``
行并复核 ``status='running'``、``lease_owner``、``lease_revision`` 与
``lease_until`` 仍活跃；任一不符抛 :class:`StaleGeneration`（事务整体回滚，无业务
写、无 spurious 终态）。锁定 ``async_jobs`` 行后，业务写与 job 状态变更在该行锁上
串行：若新 owner 先提交 ``complete_*``，旧 worker 的围栏读到非 running/较新代次而
失败；反之旧 worker 先持锁时新 owner 会阻塞至其回滚/提交后再判。

handler 选择（已在各 D handler 的 ``handle`` 包装中实现）：捕获
``StaleGeneration`` 后**返回 None**，而非向上抛。原因见 ``runtime/loop.py``：
向上抛会落入通用 ``except Exception`` → 记 ERROR ``job.handler_exception`` 后再走
``complete_failure``（同样被围栏丢弃），产生两条日志且第一条误报为未处理异常。
返回 None 则走 ``complete_success``→围栏丢弃。日志分层（N3）：handler 侧只记
``*.fenced_write_stale`` **DEBUG**（租约竞争属正常并发，不是错误），loop 的
``job.complete_stale_generation`` WARN 是唯一权威告警——避免双重日志。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Connection, Engine, text

from ...runtime.complete import StaleGeneration
from ...runtime.rows import JobRow

_FENCE = text(
    """
SELECT status, lease_owner, lease_revision,
       (lease_until IS NOT NULL AND lease_until >= CURRENT_TIMESTAMP) AS lease_live
FROM async_jobs
WHERE id = :job_id
FOR UPDATE
"""
)


@contextmanager
def fenced_business_tx(engine: Engine, job: JobRow) -> Iterator[Connection]:
    """在仍持有 ``job`` 当前租约代次的前提下，提供一个可做业务写的事务连接。

    退出时（正常）提交；任一围栏不符抛 :class:`StaleGeneration` 并回滚。
    """
    with engine.begin() as conn:
        row = conn.execute(_FENCE, {"job_id": job.id}).mappings().first()
        if (
            row is None
            or row["status"] != "running"
            or row["lease_owner"] != job.lease_owner
            or int(row["lease_revision"]) != int(job.lease_revision)
            or not row["lease_live"]
        ):
            raise StaleGeneration(
                f"job {job.id} stale lease on fenced business write"
                f" (owner={job.lease_owner}, revision={job.lease_revision})"
            )
        yield conn
