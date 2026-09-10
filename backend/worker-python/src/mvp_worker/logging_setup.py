"""结构化 JSON 日志（stdlib logging + 自定义 formatter）。

规则（DD 8/config、任务书 #10）：
- 每行一个 JSON 对象：``ts, level, event`` + 适用的关联字段
  ``workerId, jobId, jobType, dedupKey, leaseRevision, attemptCount, inputRevision``。
- 绝不输出 payload 内容、照片、凭据、供应商密钥、堆栈细节；异常只记类名/截断消息。
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_MAX_MSG = 500


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "event": record.getMessage()[:_MAX_MSG],
        }
        fields = getattr(record, "_mvp", None)
        if fields:
            entry.update(fields)
        exc_type = record.exc_info[0] if record.exc_info else None
        if exc_type is not None:
            # 只保留异常类名，不落堆栈（防泄漏 SQL 参数等细节）
            entry["errorClass"] = exc_type.__name__
        return json.dumps(entry, ensure_ascii=False, default=str)


def mlog(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """记录结构化事件；fields 为 camelCase 关联字段（None 自动剔除）。"""
    clean = {k: v for k, v in fields.items() if v is not None}
    logger.log(level, event, extra={"_mvp": clean})


def setup_logging(level: int = logging.INFO) -> None:
    """配置 ``mvp_worker`` logger（幂等）。不劫持 root logger。"""
    root = logging.getLogger("mvp_worker")
    if getattr(root, "_mvp_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False
    root._mvp_configured = True  # type: ignore[attr-defined]
