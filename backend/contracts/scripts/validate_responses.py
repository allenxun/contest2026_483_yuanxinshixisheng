#!/usr/bin/env python3
"""Strict OAS response-schema validation for the echo-jobs GET 200 body.

The structural validator (openapi_spec_validator) only proves the document is
well-formed; it does NOT prove a real response body conforms. This script
resolves the ACTUAL response schema from openapi.yaml (no hardcoded copy) and
validates captured/real bodies against it.

OpenAPI 3.0.3 -> JSON Schema 2020-12 conversion is hand-rolled (no new pip
deps; jsonschema + pyyaml already ship in the contracts venv) and covers exactly
the constructs used by the validated paths:
  $ref (within-document, chained), type, nullable (3.0.3 semantics: type union
  null when nullable:true IN THE SAME Schema Object), enum, properties,
  required, additionalProperties, items, allOf/oneOf/anyOf, plus pass-through
  scalar keywords (format/pattern/min*/max*).

CLI:
    python3 scripts/validate_responses.py <body.json> ...   # exit 0 iff all valid
    python3 scripts/validate_responses.py --selftest        # bundled fixtures,
                                                            # positives PASS + negatives REJECTED
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Callable

import yaml
from jsonschema import Draft202012Validator

CONTRACTS = pathlib.Path(__file__).resolve().parent.parent
OPENAPI_FILE = CONTRACTS / "openapi" / "openapi.yaml"
RESPONSES_DIR = CONTRACTS / "samples" / "responses"

ECHO_VIEW_PATH = "/api/v1/system/echo-jobs/{jobId}"

# Fixtures bundled with expected outcomes. Positive = must validate; negative =
# must be REJECTED (proves the validator discriminates, not accepts everything).
#
# echo-job-view-retryable.json is coherent with worker semantics: a retryable
# failure is re-queued (status=queued, finishedAt=null) while last_error carries
# retryable=true; reason=internal because the runtime's generic HANDLER_ERROR
# code is not on the safe whitelist.
POSITIVES = (
    "echo-job-view-succeeded.json",
    "echo-job-view-failed.json",
    "echo-job-view-retryable.json",
)
NEGATIVES = (
    "echo-job-view-unknown-field.json",
    "echo-job-view-bad-enum.json",
    "echo-job-view-null-in-nonnullable.json",
)


def _resolve_pointer(doc: Any, ref: str) -> Any:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported external $ref: {ref}")
    node = doc
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def convert(node: Any, doc: Any, seen: tuple[str, ...] = ()) -> Any:
    """OpenAPI 3.0.3 schema node -> JSON Schema 2020-12 (refs inlined)."""
    if isinstance(node, bool) or not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str):
        if ref in seen:
            raise ValueError(f"cyclic $ref: {ref}")
        target = convert(_resolve_pointer(doc, ref), doc, seen + (ref,))
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        if not siblings:
            return target
        return {"allOf": [target, convert(siblings, doc, seen)]}

    out: dict = {}
    nullable = node.get("nullable") is True
    for key, value in node.items():
        if key == "nullable":
            continue
        if key == "properties":
            out[key] = {pk: convert(pv, doc, seen) for pk, pv in value.items()}
        elif key == "items":
            out[key] = convert(value, doc, seen)
        elif key == "additionalProperties":
            out[key] = convert(value, doc, seen) if isinstance(value, dict) else value
        elif key in ("allOf", "oneOf", "anyOf"):
            out[key] = [convert(x, doc, seen) for x in value]
        elif key == "not":
            out[key] = convert(value, doc, seen)
        else:
            out[key] = value

    if nullable:
        declared = out.get("type")
        if isinstance(declared, str):
            out["type"] = [declared, "null"]
        elif isinstance(declared, list):
            if "null" not in declared:
                out["type"] = declared + ["null"]
        # else: OAS 3.0.3 `nullable` has NO effect without a `type` in this same
        # Schema Object (e.g. allOf/oneOf/anyOf + $ref + nullable). Do NOT broaden
        # to `{"anyOf": [..., null]}` — that masks the exact defect this validator
        # must catch: such schemas must REJECT null.
    return out


def _load_openapi() -> Any:
    return yaml.safe_load(OPENAPI_FILE.read_text("utf-8"))


def echo_response_schema(doc: Any = None) -> dict:
    """Resolve GET echo-jobs 200 application/json schema straight from the doc."""
    if doc is None:
        doc = _load_openapi()
    node = doc["paths"][ECHO_VIEW_PATH]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    return convert(node, doc)


def build_validator() -> Draft202012Validator:
    return Draft202012Validator(echo_response_schema())


STATUS_VALID = "valid"
STATUS_SCHEMA_INVALID = "schema_invalid"
STATUS_LOAD_ERROR = "load_error"


def validate_path(path: pathlib.Path, validator: Draft202012Validator) -> tuple[str, str]:
    """Returns (status, detail) with status in valid|schema_invalid|load_error.

    load_error (unreadable/malformed JSON) is a HARNESS failure, never a schema
    rejection: callers must NOT count it as a discriminating negative.
    """
    try:
        instance = json.loads(pathlib.Path(path).read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return STATUS_LOAD_ERROR, f"cannot read/parse JSON: {exc}"
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if not errors:
        return STATUS_VALID, ""
    detail = "; ".join(
        f"{e.json_path or '$'}: {e.validator or 'schema'} violated" for e in errors[:4]
    )
    return STATUS_SCHEMA_INVALID, detail


def _accepts(schema: Any, instance: Any) -> bool:
    return Draft202012Validator(schema).is_valid(instance)


def run_discrimination(emit) -> tuple[int, int]:
    """Prove the converter distinguishes the OLD broken nullable shape from the
    correct inline one. OAS 3.0.3: allOf+$ref+nullable WITHOUT local type must
    REJECT null (no null union); inline type+nullable must ACCEPT null."""
    old_doc = {"components": {"schemas": {"X": {
        "type": "object", "properties": {"a": {"type": "string"}},
        "required": ["a"], "additionalProperties": False}}}}
    old_schema = convert(
        {"allOf": [{"$ref": "#/components/schemas/X"}], "nullable": True}, old_doc)
    new_schema = convert(
        {"type": "object", "nullable": True, "properties": {"a": {"type": "string"}},
         "required": ["a"], "additionalProperties": False}, {})

    passed = failed = 0

    def check(label: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            emit(label, True, "")
        else:
            failed += 1
            emit(label, False, "discrimination broken")

    check("nullable-shape: old allOf+$ref+nullable REJECTS null",
          not _accepts(old_schema, None))
    check("nullable-shape: old allOf+$ref+nullable ACCEPTS conforming object",
          _accepts(old_schema, {"a": "x"}))
    check("nullable-shape: new inline type+nullable ACCEPTS null",
          _accepts(new_schema, None))
    check("nullable-shape: new inline type+nullable ACCEPTS conforming object",
          _accepts(new_schema, {"a": "x"}))
    return passed, failed


def run_selftest(emit) -> tuple[int, int]:
    """emit(label, passed, detail). Returns (passed_checks, failed_checks)."""
    validator = build_validator()
    passed = failed = 0
    for name in POSITIVES:
        status, detail = validate_path(RESPONSES_DIR / name, validator)
        if status == STATUS_VALID:
            passed += 1
            emit(f"responses/{name} (positive accepted)", True, "")
        else:
            failed += 1
            emit(f"responses/{name} (positive accepted)", False,
                 detail if status == STATUS_SCHEMA_INVALID
                 else f"HARNESS: fixture did not load/parse ({detail})")
    for name in NEGATIVES:
        status, detail = validate_path(RESPONSES_DIR / name, validator)
        if status == STATUS_SCHEMA_INVALID:
            passed += 1
            emit(f"responses/{name} (negative rejected)", True, "")
        elif status == STATUS_LOAD_ERROR:
            failed += 1
            emit(f"responses/{name} (negative rejected)", False,
                 f"HARNESS: fixture did not load/parse ({detail})")
        else:
            failed += 1
            emit(f"responses/{name} (negative rejected)", False,
                 "validator ACCEPTED an invalid body (no discrimination)")
    dpassed, dfailed = run_discrimination(emit)
    return passed + dpassed, failed + dfailed


def _cli_selftest() -> int:
    def emit(label: str, passed: bool, detail: str) -> None:
        print(("ok   " if passed else "FAIL ") + label + ("" if passed else f": {detail}"))

    passed, failed = run_selftest(emit)
    print(f"\nselftest: {passed} checks passed, {failed} failed "
          f"({len(POSITIVES)} positives, {len(NEGATIVES)} negatives, "
          f"4 nullable-shape discrimination)")
    print("RESULT: " + ("PASS" if failed == 0 else "FAIL"))
    return 0 if failed == 0 else 1


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return _cli_selftest()
    if not argv:
        print("usage: validate_responses.py <body.json>... | --selftest", file=sys.stderr)
        return 2
    validator = build_validator()
    rc = 0
    for raw in argv:
        path = pathlib.Path(raw)
        status, detail = validate_path(path, validator)
        if status == STATUS_VALID:
            print(f"ok   {path}")
        elif status == STATUS_LOAD_ERROR:
            print(f"FAIL {path}: HARNESS load error: {detail}")
            rc = 1
        else:
            print(f"FAIL {path}: {detail}")
            rc = 1
    print("RESULT: " + ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
