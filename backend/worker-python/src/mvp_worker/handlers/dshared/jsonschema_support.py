"""payload 契约严格校验（draft 2020-12，common.json ``$ref`` 确定性内联）。

只输出 json_path + 校验关键字，**绝不回显 payload 值**（DD 9.1 / 日志禁内容）。
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .. import UnsupportedPayload

_COMMON_REF_BASE = "urn:mvp:contracts:schemas:common.json"


def contracts_dir() -> Path:
    """契约目录：env ``MVP_CONTRACTS_DIR`` 覆盖；默认回溯到本仓 backend/contracts。"""
    env = os.environ.get("MVP_CONTRACTS_DIR")
    if env:
        return Path(env)
    # dshared/ -> handlers/ -> mvp_worker/ -> src/ -> worker-python/ -> backend/ -> repo
    return Path(__file__).resolve().parents[6] / "backend" / "contracts"


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


_cache: dict[str, Draft202012Validator] = {}
_cache_lock = threading.Lock()


def load_payload_validator(schema_filename: str) -> Draft202012Validator:
    """加载并缓存 payload schema 校验器（common.json 内联）。"""
    with _cache_lock:
        cached = _cache.get(schema_filename)
        if cached is not None:
            return cached
        common = _load_schema("common.json")
        schema = _inline_refs(_load_schema(schema_filename), common)
        validator = Draft202012Validator(schema)
        _cache[schema_filename] = validator
        return validator


def validate_payload(
    validator: Draft202012Validator, payload: object, schema_filename: str
) -> None:
    """严格校验；违反 → :class:`UnsupportedPayload`（消息只含路径与关键字）。"""
    if not isinstance(payload, dict):
        raise UnsupportedPayload(f"{schema_filename}: payload: type violated")
    errors = sorted(
        validator.iter_errors(payload), key=lambda e: list(e.absolute_path)
    )
    if errors:
        joined = "; ".join(
            f"{e.json_path or '$'}: {e.validator or 'schema'} violated"
            for e in errors[:5]
        )
        raise UnsupportedPayload(f"{schema_filename}: {joined}")
