#!/usr/bin/env python3
"""B 包验收脚本辅助（L6）：JSON 取值/形状断言、错误信封校验、契约码白名单、
dev/test 证明铸造（d1 格式）。纯标准库 + PyYAML（contracts .venv）。

约定：调用方通过环境变量传 JSON：
  JGET_JSON  —— 直接传 JSON 文本
  JGET_FILE  —— 传 JSON 文件路径（优先）
用法示例：
  JGET_JSON='{"a":{"b":1}}' b-helper.py jget a.b
  JGET_FILE=body.json b-helper.py mask
  b-helper.py envelope body.json
  b-helper.py contract-hit m1A01CreateMemberAccessGrant INVALID_INPUT
  echo '{"purpose":"pairing",...}' | b-helper.py proof [--version d2] [--tamper]
  b-helper.py sha256 face.bin
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import uuid
from typing import Any, NoReturn

CONTRACTS = os.environ.get("MVP_CONTRACTS_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "contracts"
)
OPENAPI = os.path.join(CONTRACTS, "openapi", "openapi.yaml")

DEV_TEST_KEY = "mvp-b-dev-test-proof-key-v1"
ALLOWED_ERROR_KEYS = {"code", "message", "retryable", "details"}


def _die(msg: str) -> NoReturn:
    sys.stderr.write("HELPER-FAIL: " + msg + "\n")
    sys.exit(1)


def _load() -> Any:
    path = os.environ.get("JGET_FILE")
    if path:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if "JGET_JSON" in os.environ:
        return json.loads(os.environ["JGET_JSON"])
    return json.loads(sys.stdin.read())


def _walk(cur: Any, path: str) -> Any:
    if path == "":
        return cur
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def _fmt(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def cmd_jget(argv: list[str]) -> int:
    if len(argv) != 1:
        _die("jget <dotpath>")
    try:
        print(_fmt(_walk(_load(), argv[0])))
    except (KeyError, IndexError, ValueError) as exc:
        _die(f"path {argv[0]} not found: {exc}")
    return 0


def cmd_keys(argv: list[str]) -> int:
    path = argv[0] if argv else ""
    try:
        node = _walk(_load(), path)
    except (KeyError, IndexError, ValueError) as exc:
        _die(f"path {path} not found: {exc}")
    if not isinstance(node, dict):
        _die(f"node at {path!r} is not an object")
    print(",".join(sorted(node.keys())))
    return 0


def cmd_assert_keys(argv: list[str]) -> int:
    if len(argv) != 2:
        _die("assert-keys <dotpath> <comma-keys>")
    path, expected = argv[0], argv[1]
    try:
        node = _walk(_load(), path)
    except (KeyError, IndexError, ValueError) as exc:
        _die(f"path {path} not found: {exc}")
    if not isinstance(node, dict):
        _die(f"node at {path!r} is not an object (got {type(node).__name__})")
    want = set(k for k in expected.split(",") if k != "") if expected else set()
    got = set(node.keys())
    if got != want:
        _die(f"field set mismatch at {path!r}: got {sorted(got)} want {sorted(want)}")
    print("field-set OK: " + ",".join(sorted(got)))
    return 0


def cmd_envelope(argv: list[str]) -> int:
    """校验错误信封 {requestId,error{code,message,retryable,details?}}，打印 code。"""
    if len(argv) != 1:
        _die("envelope <file>")
    with open(argv[0], "r", encoding="utf-8") as fh:
        raw = fh.read()
    try:
        obj = json.loads(raw)
    except ValueError as exc:
        _die(f"not JSON: {exc}")
    if not isinstance(obj, dict):
        _die("error body is not an object")
    if set(obj.keys()) != {"requestId", "error"}:
        _die(f"envelope top-level keys must be exactly requestId,error; got {sorted(obj.keys())}")
    if not isinstance(obj["requestId"], str) or not obj["requestId"]:
        _die("requestId must be a non-empty string")
    err = obj["error"]
    if not isinstance(err, dict):
        _die("error must be an object")
    missing = {"code", "message", "retryable"} - set(err.keys())
    if missing:
        _die(f"error missing required keys {sorted(missing)}")
    extra = set(err.keys()) - ALLOWED_ERROR_KEYS
    if extra:
        _die(f"error has unexpected keys {sorted(extra)}")
    if not isinstance(err["code"], str) or not err["code"]:
        _die("error.code must be a non-empty string")
    if not isinstance(err["message"], str):
        _die("error.message must be a string")
    if not isinstance(err["retryable"], bool):
        _die("error.retryable must be a boolean")
    if "details" in err and err["details"] is not None and not isinstance(err["details"], dict):
        _die("error.details must be an object or null")
    print(err["code"])
    return 0


def cmd_mask(argv: list[str]) -> int:
    """把每个请求的 requestId 值替换为 <requestId> 后逐字节输出，供不可区分比较。"""
    with open(argv[0], "rb") as fh:
        raw = fh.read()
    try:
        obj = json.loads(raw)
    except ValueError:
        _die("not JSON")
    rid = obj.get("requestId") if isinstance(obj, dict) else None
    if not isinstance(rid, str) or not rid:
        _die("no requestId to mask")
    sys.stdout.write(raw.decode("utf-8").replace(rid, "<requestId>"))
    return 0


def cmd_json_get_file(argv: list[str]) -> int:
    if len(argv) != 2:
        _die("json-get-file <file> <dotpath>")
    with open(argv[0], "r", encoding="utf-8") as fh:
        obj = json.load(fh)
    try:
        print(_fmt(_walk(obj, argv[1])))
    except (KeyError, IndexError, ValueError) as exc:
        _die(f"path {argv[1]} not found: {exc}")
    return 0


def _load_openapi() -> dict:
    import yaml  # provided by contracts/.venv

    with open(OPENAPI, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _op_codes() -> dict[str, list[str]]:
    spec = _load_openapi()
    out: dict[str, list[str]] = {}
    for _path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for _method, op in item.items():
            if isinstance(op, dict) and "operationId" in op:
                out[op["operationId"]] = list(op.get("x-error-codes") or [])
    return out


def cmd_contract_hit(argv: list[str]) -> int:
    if len(argv) != 2:
        _die("contract-hit <operationId> <code>")
    op, code = argv
    codes = _op_codes()
    if op not in codes:
        _die(f"unknown operationId {op}")
    if code not in codes[op]:
        _die(f"code {code} not declared for {op}; declared={codes[op]}")
    print(f"{op}: {code} declared")
    return 0


def cmd_contract_list(argv: list[str]) -> int:
    codes = _op_codes()
    ops = argv if argv else sorted(codes)
    for op in ops:
        if op not in codes:
            _die(f"unknown operationId {op}")
        print(op + "=" + ",".join(codes[op]))
    return 0


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _sign(payload_b64: str) -> str:
    mac = hmac.new(DEV_TEST_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256)
    return _b64url(mac.digest())


def cmd_proof(argv: list[str]) -> int:
    version = "d1"
    tamper = False
    i = 0
    while i < len(argv):
        if argv[i] == "--version":
            version = argv[i + 1]
            i += 2
        elif argv[i] == "--tamper":
            tamper = True
            i += 1
        else:
            _die(f"proof: unknown arg {argv[i]}")
    payload: dict[str, Any] = json.loads(sys.stdin.read())
    if "exp" not in payload or payload["exp"] is None:
        import time

        payload["exp"] = int(time.time()) + 300
    if not payload.get("nonce"):
        payload["nonce"] = str(uuid.uuid4())
    payload_b64 = _b64url(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    sig = _sign(payload_b64)
    if tamper:
        sig = sig[:-1] + ("A" if sig[-1] != "A" else "B")
    print(f"{version}.{payload_b64}.{sig}")
    return 0


def cmd_sha256(argv: list[str]) -> int:
    if len(argv) != 1:
        _die("sha256 <file>")
    with open(argv[0], "rb") as fh:
        print(hashlib.sha256(fh.read()).hexdigest())
    return 0


COMMANDS = {
    "jget": cmd_jget,
    "keys": cmd_keys,
    "assert-keys": cmd_assert_keys,
    "envelope": cmd_envelope,
    "mask": cmd_mask,
    "json-get-file": cmd_json_get_file,
    "contract-hit": cmd_contract_hit,
    "contract-list": cmd_contract_list,
    "proof": cmd_proof,
    "sha256": cmd_sha256,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        _die("usage: b-helper.py <" + "|".join(sorted(COMMANDS)) + "> ...")
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
