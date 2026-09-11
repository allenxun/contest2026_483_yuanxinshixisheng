"""``payload-notification-deliver.json`` 严格校验（复用 A system_echo 的
$ref 内联写法；**不修改 system_echo.py**）。

payload 契约（C3）：只允许 ``schema_version``(const 1) + ``notification_id``，
``additionalProperties:false``。违规 → UnsupportedPayload → 运行时
failed/UNSUPPORTED_CONTRACT，不重试。
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any, Optional

from jsonschema import Draft202012Validator

PAYLOAD_SCHEMA_FILE = "payload-notification-deliver.json"
_COMMON_REF_BASE = "urn:mvp:contracts:schemas:common.json"


def contracts_dir() -> Path:
    env = os.environ.get("MVP_CONTRACTS_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[5] / "backend" / "contracts"


def _load_schema(filename: str) -> dict[str, Any]:
    path = contracts_dir() / "schemas" / filename
    with path.open("r", encoding="utf-8") as fh:
        return json.loads(fh.read())


def _resolve_common_ref(ref: str, common: dict[str, Any]) -> dict[str, Any]:
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


class PayloadValidationError(ValueError):
    """payload 违反契约（由 handler 转成 UnsupportedPayload）。"""


class NotificationDeliverPayloadValidator:
    """惰性构建并缓存 draft 2020-12 validator（线程安全）。"""

    def __init__(self) -> None:
        self._validator: Optional[Draft202012Validator] = None
        self._lock = threading.Lock()

    def _get_validator(self) -> Draft202012Validator:
        if self._validator is None:
            with self._lock:
                if self._validator is None:
                    common = _load_schema("common.json")
                    schema = _inline_refs(_load_schema(PAYLOAD_SCHEMA_FILE), common)
                    self._validator = Draft202012Validator(schema)
        return self._validator

    def validate(self, payload: object) -> None:
        if not isinstance(payload, dict):
            raise PayloadValidationError("payload: not an object")
        validator = self._get_validator()
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
        if errors:
            # 只输出错误路径与校验关键字，绝不输出 payload 值（日志禁内容）
            joined = "; ".join(
                f"{e.json_path or '$'}: {e.validator or 'schema'} violated" for e in errors[:5]
            )
            raise PayloadValidationError(f"{PAYLOAD_SCHEMA_FILE}: {joined}")
