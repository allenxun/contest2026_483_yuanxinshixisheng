#!/usr/bin/env python3
"""Dependency-free RFC 8785 (JSON Canonicalization Scheme) reference implementation.

Part of the MVP foundation contract (backend/contracts). Both the Java web
service and the Python worker must reproduce this canonicalization for
T13 payload_hash and cross-language contract tests; see
backend/contracts/canonicalization.md for the request-object spec and
backend/contracts/samples/canonicalization/vectors.json for shared vectors.

CLI:
    python3 scripts/jcs.py hash <file.json>      # print lowercase sha256 hex
    python3 scripts/jcs.py serialize <file.json> # print canonical UTF-8 bytes
    python3 scripts/jcs.py selftest              # ES6 Number::toString pairs self-check

Rules implemented (RFC 8785):
  * object members sorted by key in UTF-16 code-unit order (ES6 sort),
    serialized with no whitespace;
  * arrays keep their order (order-significant);
  * strings serialized as minimal-escape JSON strings, output UTF-8 (U+FEFF
    and other non-ASCII characters are NOT escaped);
  * numbers serialized per ECMAScript Number::toString (finite only;
    -0 -> "0"; integral doubles -> canonical decimal without leading zeros;
    exponent form "e+XX"/"e-XX" without leading zeros in the exponent);
  * duplicate keys in the input JSON object are rejected (JCS requires
    sequences of unique names);
  * lone surrogates in keys/values are rejected: they cannot be encoded as
    valid UTF-8 and never appear in our contract data.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys

MAX_SAFE_INTEGER = 9007199254740991  # 2**53 - 1


class CanonicalizationError(ValueError):
    """Raised when input cannot be canonicalized per RFC 8785."""


def _utf16_code_units(s: str) -> list[int]:
    units: list[int] = []
    for ch in s:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            raise CanonicalizationError(
                f"lone surrogate U+{cp:04X} in string {s!r}; not representable"
            )
        if cp > 0xFFFF:
            cp -= 0x10000
            units.append(0xD800 + (cp >> 10))
            units.append(0xDC00 + (cp & 0x3FF))
        else:
            units.append(cp)
    return units


def _sort_key(s: str) -> list[int]:
    return _utf16_code_units(s)


_SHORT_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _serialize_string(s: str) -> str:
    out = ['"']
    for ch in s:
        esc = _SHORT_ESCAPES.get(ch)
        if esc is not None:
            out.append(esc)
            continue
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            raise CanonicalizationError(
                f"lone surrogate U+{cp:04X} in string {s!r}; not representable"
            )
        if cp < 0x20:
            out.append("\\u%04x" % cp)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _number_to_string(value: float | int) -> str:
    """ECMAScript Number::toString(value) for finite doubles (radix 10).

    Python ``int`` values outside the exact-double range are rejected: JSON
    numbers in our contracts are either small integers (schema_version) or
    arrive as bigint-as-string, never as > 2**53 JSON numbers.
    """
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalizationError(
                f"JSON number {value} exceeds the safe double range; "
                "transport big integers as strings"
            )
        return str(value)
    f = value
    if math.isnan(f) or math.isinf(f):
        raise CanonicalizationError("NaN/Infinity are not serializable per RFC 8785")
    if f == 0.0:
        return "0"  # covers -0 as well
    d = float(f)
    if d.is_integer() and abs(d) < 1e21:
        return str(int(d))
    # Shortest round-trip decimal digits (Python repr == JS DoubleToRawPrecision).
    a = abs(d)
    s = repr(a)
    if "e" in s:
        mant, exp = s.split("e")
        exp = int(exp)
    else:
        mant, exp = s, 0
    int_part, _, frac_part = mant.partition(".")
    raw = int_part + frac_part
    digits = raw.lstrip("0") or "0"
    # n: position of the decimal point relative to the digit string,
    # i.e. value == 0.digits * 10**n. Before stripping, value ==
    # 0.raw * 10**(len(int_part) + exp); dropping z leading zeros from the
    # digit string shifts the decimal point z places left (fixes |v| < 1,
    # where int_part is "0" — e.g. 0.5 -> n=0, not n=1).
    n = len(int_part) + exp - (len(raw) - len(digits))
    # Strip trailing zeros from digits, adjusting nothing about n (they were
    # never trailing in the integer sense).
    digits = digits.rstrip("0") or "0"
    k = len(digits)
    sign = "-" if d < 0 else ""
    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + digits
    if k == 1:
        m = digits
    else:
        m = digits[0] + "." + digits[1:]
    e = n - 1
    return sign + m + ("e+" if e >= 0 else "e-") + str(abs(e))


# ECMAScript Number::toString pairs verified against the ES6 spec (authoritative
# for RFC 8785 §4.2.2). 9007199254740992 is the *double* 2**53 (integer literals
# above 2**53-1 are rejected by this contract: bigint-as-string, see docs).
_NUMBER_SELFTEST_PAIRS: list[tuple[float, str]] = [
    (0.0, "0"),
    (-0.0, "0"),
    (1.0, "1"),
    (0.5, "0.5"),
    (0.000123, "0.000123"),
    (1e-4, "0.0001"),
    (1e-5, "0.00001"),
    (1e-6, "0.000001"),
    (1e-7, "1e-7"),
    (1e20, "100000000000000000000"),
    (1e21, "1e+21"),
    (1e23, "1e+23"),
    (1e30, "1e+30"),
    (3.14159, "3.14159"),
    (123.456, "123.456"),
    (9007199254740992.0, "9007199254740992"),
    (1.7976931348623157e308, "1.7976931348623157e+308"),
    (2.2250738585072014e-308, "2.2250738585072014e-308"),
    (0.1, "0.1"),
    (-0.5, "-0.5"),
    (1e-3, "0.001"),
    (2.5e-8, "2.5e-8"),
    (1234.5, "1234.5"),
]


def selftest() -> int:
    """Assert ES6 Number::toString pairs and a few structural rules. 0 = pass."""
    failures = 0
    for value, expected in _NUMBER_SELFTEST_PAIRS:
        got = _number_to_string(value)
        if got != expected:
            failures += 1
            print(f"FAIL: {value!r} -> {got!r}, expected {expected!r}")
    checks = [
        (canonicalize({"b": 1, "a": [2, {"d": None, "c": True}]}),
         '{"a":[2,{"c":true,"d":null}],"b":1}'),
        (canonicalize({"成员": "张三", "A": 1}), '{"A":1,"成员":"张三"}'),
    ]
    for got, expected in checks:
        if got != expected:
            failures += 1
            print(f"FAIL: structural {got!r} != {expected!r}")
    try:
        load_strict('{"a":1,"a":2}')
        failures += 1
        print("FAIL: duplicate keys must be rejected")
    except CanonicalizationError:
        pass
    total = len(_NUMBER_SELFTEST_PAIRS) + len(checks) + 1
    if failures:
        print(f"selftest: {failures}/{total} FAILED")
        return 1
    print(f"selftest: PASS ({total} checks, {len(_NUMBER_SELFTEST_PAIRS)} number pairs)")
    return 0


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise CanonicalizationError(f"duplicate JSON object key {key!r}")
        seen.add(key)
    return dict(pairs)


def canonicalize(value: object) -> str:
    """Return the RFC 8785 canonical serialization of a parsed JSON value."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _serialize_string(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _number_to_string(value)
    if isinstance(value, list):
        return "[" + ",".join(canonicalize(item) for item in value) + "]"
    if isinstance(value, dict):
        parts = []
        for key in sorted(value.keys(), key=_sort_key):
            parts.append(_serialize_string(key) + ":" + canonicalize(value[key]))
        return "{" + ",".join(parts) + "}"
    raise CanonicalizationError(f"unsupported JSON value type: {type(value).__name__}")


def canonicalize_bytes(value: object) -> bytes:
    return canonicalize(value).encode("utf-8")


def sha256_hex(value: object) -> str:
    return hashlib.sha256(canonicalize_bytes(value)).hexdigest()


def load_strict(text: str) -> object:
    """Parse JSON rejecting duplicate object keys (JCS precondition)."""
    return json.loads(text, object_pairs_hook=_reject_duplicate_pairs)


def _usage() -> "None":
    prog = sys.argv[0]
    print(f"usage: python3 {prog} hash <file.json>", file=sys.stderr)
    print(f"       python3 {prog} serialize <file.json>", file=sys.stderr)
    print(f"       python3 {prog} selftest", file=sys.stderr)


def main(argv: list[str]) -> int:
    if argv == ["selftest"]:
        return selftest()
    if len(argv) != 2 or argv[0] not in ("hash", "serialize"):
        _usage()
        return 2
    mode, path = argv[0], argv[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            value = load_strict(fh.read())
        if mode == "hash":
            print(sha256_hex(value))
        else:
            sys.stdout.buffer.write(canonicalize_bytes(value) + b"\n")
        return 0
    except (OSError, json.JSONDecodeError, CanonicalizationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
