"""``system.echo``：A 包最小跨语言测试任务（decisions #4）。

payload 权威校验 = backend/contracts/schemas/payload-system-echo.json
（draft 2020-12，additionalProperties=false，schema_version const 1）。
handler 只做 trivial 工作（sleep 0.05s）模拟外部调用 + 协作式租约检查；
无业务表写入（HandlerResult.business_tx=None）。
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from jsonschema import Draft202012Validator

from . import HandlerResult, HandlerContext, UnsupportedPayload
from ..runtime.rows import JobRow

ECHO_JOB_TYPE = "system.echo"
_PAYLOAD_SCHEMA_FILE = "payload-system-echo.json"
_COMMON_REF_BASE = "urn:mvp:contracts:schemas:common.json"


def contracts_dir() -> Path:
    """契约目录：env ``MVP_CONTRACTS_DIR`` 覆盖；默认按 src 布局回溯到
    本仓 backend/contracts（只读引用，Worker 从不写契约）。"""
    env = os.environ.get("MVP_CONTRACTS_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[5] / "backend" / "contracts"


def _load_schema(filename: str) -> dict[str, Any]:
    path = contracts_dir() / "schemas" / filename
    with path.open("r", encoding="utf-8") as fh:
        return json.loads(fh.read())


def _resolve_common_ref(ref: str, common: dict[str, Any]) -> dict[str, Any]:
    """解析 ``urn:...common.json#/$defs/<name>`` 形式的引用（契约 schema 仅用
    这一层级的 $ref，故做确定性内联，避免各 jsonschema 版本注册表 API 差异）。"""
    if not ref.startswith(_COMMON_REF_BASE + "#"):
        raise ValueError(f"unsupported $ref: {ref}")
    node: Any = common
    for part in ref[len(_COMMON_REF_BASE) + 1 :].strip("/").split("/"):
        node = node[part]
    return node


def _inline_refs(node: Any, common: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_inline_refs(x, common) for x in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith(_COMMON_REF_BASE + "#"):
        merged = _inline_refs(copy.deepcopy(_resolve_common_ref(ref, common)), common)
        for key, value in node.items():
            if key != "$ref":
                merged[key] = _inline_refs(value, common)
        return merged
    return {k: _inline_refs(v, common) for k, v in node.items()}


class EchoHandler:
    name = "system-echo"

    def __init__(self) -> None:
        self._validator: Optional[Draft202012Validator] = None
        self._lock = threading.Lock()

    def _get_validator(self) -> Draft202012Validator:
        if self._validator is None:
            with self._lock:
                if self._validator is None:
                    common = _load_schema("common.json")
                    schema = _inline_refs(_load_schema(_PAYLOAD_SCHEMA_FILE), common)
                    self._validator = Draft202012Validator(schema)
        return self._validator

    def validate(self, payload: object) -> None:
        if not isinstance(payload, dict):
            raise UnsupportedPayload("payload: not an object")
        validator = self._get_validator()
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
        if errors:
            # 只输出错误路径与校验关键字，绝不输出 payload 值（日志禁内容）
            joined = "; ".join(
                f"{e.json_path or '$'}: {e.validator or 'schema'} violated" for e in errors[:5]
            )
            raise UnsupportedPayload(f"payload-system-echo.json: {joined}")

    def handle(self, ctx: HandlerContext, job: JobRow) -> Optional[HandlerResult]:
        # 模拟 trivial 外部工作；协作式检查租约（丢失租约后不再做任何提交）
        time.sleep(0.05)
        if ctx.abort_event.is_set():
            return None
        # echo 无业务表写入；结果即任务状态本身
        return HandlerResult(business_tx=None)


handler = EchoHandler()
