#!/usr/bin/env python3
"""Validate one JSON payload file against a contracts schema (draft 2020-12,
cross-file $refs resolved from the schemas dir). Used by run-acceptance.sh step
f8 to prove the Java-written async_jobs.payload satisfies the contract schema
with the Python-side validator.

usage: validate_payload.py <payload.json> <schema.json> <contracts-dir>
"""
from __future__ import annotations

import json
import pathlib
import sys

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


def main(argv: list[str]) -> int:
    payload_path, schema_path, contracts_dir = map(pathlib.Path, argv)
    schemas_dir = contracts_dir / "schemas"
    resources = []
    for p in sorted(schemas_dir.glob("*.json")):
        contents = json.loads(p.read_text("utf-8"))
        sid = contents.get("$id")
        if sid:
            resources.append((sid, Resource.from_contents(contents)))
    registry = Registry().with_resources(resources)

    schema = json.loads(schema_path.read_text("utf-8"))
    payload = json.loads(payload_path.read_text("utf-8"))
    validator = Draft202012Validator(schema, registry=registry)
    errors = sorted(validator.iter_errors(payload), key=str)
    if errors:
        for err in errors:
            print(f"FAIL {list(err.absolute_path)}: {err.message}", file=sys.stderr)
        return 1
    print(f"PASS payload valid against {schema_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
