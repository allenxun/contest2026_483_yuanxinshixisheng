#!/usr/bin/env python3
"""Verify backend/contracts/samples against the shared contract schemas.

1. Every samples/jobs/*.json payload validates against its JSON Schema
   (draft 2020-12, schemas/ directory, cross-file $refs via registry).
2. Envelope & multipart-metadata samples validate against the OpenAPI
   components/schemas they are governed by (openapi/openapi.yaml), after a
   minimal OpenAPI-3.0 -> JSON-Schema-2020-12 adaptation (nullable handling,
   component $ref rewriting).
3. Every canonicalization vector's expected_sha256 is recomputed with the
   reference RFC 8785 implementation in scripts/jcs.py.

Exit code is nonzero on any failure. Run from anywhere:
    python3 scripts/validate_samples.py
"""
from __future__ import annotations

import json
import pathlib
import sys

CONTRACTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CONTRACTS / "scripts"))

import jcs  # noqa: E402  (reference JCS implementation)
import yaml  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

SCHEMAS_DIR = CONTRACTS / "schemas"
OPENAPI_FILE = CONTRACTS / "openapi" / "openapi.yaml"
SAMPLES = CONTRACTS / "samples"

FAILURES: list[str] = []
CHECKS = 0


def fail(label: str, detail: str) -> None:
    FAILURES.append(f"{label}: {detail}")
    print(f"FAIL {label}: {detail}")


def ok(label: str) -> None:
    global CHECKS
    CHECKS += 1
    print(f"ok   {label}")


def load_json(path: pathlib.Path):
    return jcs.load_strict(path.read_text("utf-8"))


# ---------------- JSON Schema (draft 2020-12) ----------------

def jsonschema_registry() -> Registry:
    resources = []
    for p in sorted(SCHEMAS_DIR.glob("*.json")):
        contents = json.loads(p.read_text("utf-8"))
        sid = contents.get("$id")
        if not sid:
            fail("schema-ids", f"{p.name} has no $id")
            continue
        resources.append((sid, Resource.from_contents(contents)))
    return Registry().with_resources(resources)


def validate_with_jsonschema(instance, schema_uri: str, registry: Registry, label: str) -> None:
    schema_resource = registry.contents(schema_uri)
    validator = Draft202012Validator(schema_resource, registry=registry)
    errors = sorted(validator.iter_errors(instance), key=lambda e: e.json_path)
    if errors:
        fail(label, "; ".join(f"{e.json_path}: {e.message}" for e in errors[:5]))
    else:
        ok(label)


JOB_PAYLOAD_MAP = {
    "system-echo.json": "urn:mvp:contracts:schemas:payload-system-echo.json",
    "assessment-analyze.json": "urn:mvp:contracts:schemas:payload-assessment-analyze.json",
    "identity-enroll.json": "urn:mvp:contracts:schemas:payload-identity-enroll.json",
    "plan-generate.json": "urn:mvp:contracts:schemas:payload-plan-generate.json",
    "notification-deliver.json": "urn:mvp:contracts:schemas:payload-notification-deliver.json",
    "media-cleanup.json": "urn:mvp:contracts:schemas:payload-media-cleanup.json",
}


# ---------------- OpenAPI 3.0 -> JSON Schema adaptation ----------------

def openapi_to_jsonschema(node):
    """Recursively adapt OpenAPI 3.0 schema objects to draft 2020-12."""
    if isinstance(node, list):
        return [openapi_to_jsonschema(x) for x in node]
    if not isinstance(node, dict):
        return node
    node = {k: openapi_to_jsonschema(v) for k, v in node.items()}
    # rewrite component refs to absolute registry URNs
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        node["$ref"] = f"urn:mvp:contracts:openapi:{ref.rsplit('/', 1)[-1]}"
    # drop OpenAPI-only keywords unknown to strict vocabularies (harmless annotations)
    nullable = node.pop("nullable", False)
    node.pop("example", None)
    node.pop("discriminator", None)
    if nullable is True:
        if "type" in node and isinstance(node["type"], str):
            node["type"] = [node["type"], "null"]
        elif "allOf" in node:
            node = {"anyOf": [node, {"type": "null"}]}
    return node


def openapi_registry() -> Registry:
    doc = yaml.safe_load(OPENAPI_FILE.read_text("utf-8"))
    components = doc["components"]["schemas"]
    resources = []
    for name, schema in components.items():
        adapted = openapi_to_jsonschema(schema)
        adapted["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        adapted["$id"] = f"urn:mvp:contracts:openapi:{name}"
        resources.append((adapted["$id"], Resource.from_contents(adapted)))
    return Registry().with_resources(resources)


def validate_with_openapi(instance, component: str, registry: Registry, label: str) -> None:
    resource = registry.contents(f"urn:mvp:contracts:openapi:{component}")
    validator = Draft202012Validator(resource, registry=registry)
    errors = sorted(validator.iter_errors(instance), key=lambda e: e.json_path)
    if errors:
        fail(label, "; ".join(f"{e.json_path}: {e.message}" for e in errors[:5]))
    else:
        ok(label)


# ---------------- canonicalization vectors ----------------

def check_vectors() -> None:
    path = SAMPLES / "canonicalization" / "vectors.json"
    vectors = load_json(path)
    if not isinstance(vectors, list) or not vectors:
        fail("vectors", "vectors.json must be a non-empty array")
        return
    seen = set()
    for v in vectors:
        name = v.get("name", "<unnamed>")
        if name in seen:
            fail("vectors-dup-name", name)
        seen.add(name)
        actual = jcs.sha256_hex(v["input"])
        if actual != v["expected_sha256"]:
            fail(f"vector {name}", f"expected {v['expected_sha256']} got {actual}")
        else:
            ok(f"vector {name}")
    by_name = {v["name"]: v["expected_sha256"] for v in vectors}
    pairs = [
        ("nested-out-of-order-keys-a", "nested-out-of-order-keys-b-equal-hash-to-a", True),
        ("defaults-expanded-equal-pair-a", "defaults-expanded-equal-pair-b-equal-hash-to-a", True),
        ("array-order-significant-front-left-right", "array-order-significant-reversed-different-hash", False),
        ("near-collision-closure-final-count-3", "near-collision-closure-final-count-4-different-hash", False),
    ]
    for a, b, equal in pairs:
        if a not in by_name or b not in by_name:
            fail("vector-pair", f"missing {a or b}")
            continue
        if (by_name[a] == by_name[b]) != equal:
            fail("vector-pair", f"{a} vs {b}: expected equal={equal}")
        else:
            ok(f"vector pair {a} {'==' if equal else '!='} {b}")


def main() -> int:
    print("== JSON Schema (draft 2020-12) job/payload samples ==")
    reg = jsonschema_registry()
    for fname, uri in JOB_PAYLOAD_MAP.items():
        validate_with_jsonschema(load_json(SAMPLES / "jobs" / fname), uri, reg, f"samples/jobs/{fname}")
    for handoff in ("job-handoff-example.json", "echo-handoff-app-created.json",
                    "echo-handoff-gimbal-created.json"):
        validate_with_jsonschema(
            load_json(SAMPLES / "jobs" / handoff),
            "urn:mvp:contracts:schemas:job-async_jobs.json", reg,
            f"samples/jobs/{handoff}",
        )

    print("== OpenAPI components/schemas envelope & metadata samples ==")
    oreg = openapi_registry()
    validate_with_openapi(load_json(SAMPLES / "envelopes" / "success-envelope.json"), "SuccessEnvelope", oreg, "success-envelope.json")
    list_page = load_json(SAMPLES / "envelopes" / "list-page.json")
    validate_with_openapi(list_page, "SuccessEnvelope", oreg, "list-page.json (envelope)")
    validate_with_openapi(list_page["data"], "MemberAccessGrantListData", oreg, "list-page.json (data=MemberAccessGrantListData)")
    validate_with_openapi(load_json(SAMPLES / "envelopes" / "error-envelope.json"), "ErrorEnvelope", oreg, "error-envelope.json")
    err = load_json(SAMPLES / "envelopes" / "error-envelope.json")
    if err["error"]["code"] != "DEVICE_OCCUPIED":
        fail("error-envelope", "expected DEVICE_OCCUPIED sample")
    else:
        ok("error-envelope.json code=DEVICE_OCCUPIED")
    ni = load_json(SAMPLES / "envelopes" / "not-implemented-501.json")
    validate_with_openapi(ni, "ErrorEnvelope", oreg, "not-implemented-501.json (ErrorEnvelope)")
    validate_with_openapi(ni, "NotImplementedEnvelope", oreg, "not-implemented-501.json (NotImplementedEnvelope)")
    if ni["error"]["code"] != "NOT_IMPLEMENTED":
        fail("not-implemented-501", "expected code NOT_IMPLEMENTED")
    else:
        ok("not-implemented-501.json code=NOT_IMPLEMENTED")
    validate_with_openapi(load_json(SAMPLES / "multipart-metadata" / "m1a01-metadata.json"), "M1A01Metadata", oreg, "m1a01-metadata.json")
    validate_with_openapi(load_json(SAMPLES / "multipart-metadata" / "m3a01-metadata.json"), "M3A01Metadata", oreg, "m3a01-metadata.json")

    print("== canonicalization vectors (recomputed with scripts/jcs.py) ==")
    check_vectors()

    print("== strict echo-jobs 200 response schema (scripts/validate_responses.py) ==")
    import validate_responses  # noqa: E402  (same scripts/ dir)
    validate_responses.run_selftest(
        lambda label, passed, detail: ok(label) if passed else fail(label, detail or "invalid")
    )

    print(f"\n{CHECKS} checks passed, {len(FAILURES)} failed")
    if FAILURES:
        print("RESULT: FAIL", file=sys.stderr)
        return 1
    print("RESULT: PASS — all samples valid, all canonicalization vectors match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
