#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""a-reverify 哨兵：绑定本次 RUN_ID 的结算校验（matrix 级强度）。

run.sh 在驱动退出后调用本模块，只信 `reports/<RUN_ID>/reverify-sentinel.json`，
逐项校验 run_id/mode/结算集/计数和/final_exit 政策一致性；任一不符 → 退出 1
（run.sh 据此强制 4）。可单测。
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]          # backend/acceptance
REPORTS = ROOT / "reports"
LAST_RUN_FILE = REPORTS / ".last-reverify-run"
EXPECTED_TARGETED = frozenset({f"RV-{i}" for i in range(1, 10)}
                              | {"CLEANUP", "CLEANUP-ports"})
KNOWN = ("pass", "fail", "blocked", "info")


def expected_exit(counts: dict, complete: bool) -> int:
    if counts.get("fail", 0) > 0 or counts.get("blocked", 0) > 0:
        return 1
    return 0 if complete else 4


def write_sentinel(run_id: str, settle: dict, rc: int, reports_dir: pathlib.Path | None = None) -> pathlib.Path:
    reports_dir = reports_dir or REPORTS
    counts = {k: int(settle["counts"].get(k, 0)) for k in KNOWN}
    complete = (not settle.get("missing") and not settle.get("extra")
                and not settle.get("duplicates") and not settle.get("unknown_status")
                and sum(counts.values()) == settle.get("rows") == settle.get("settled"))
    data = {"run_id": run_id, "mode": "targeted-reverify", "settled": settle["settled"],
            "expected": len(EXPECTED_TARGETED), "missing": settle.get("missing", []),
            "extra": settle.get("extra", []), "duplicates": settle.get("duplicates", []),
            "unknown_status": settle.get("unknown_status", []), "counts": counts,
            "counts_sum": sum(counts.values()), "rows": settle.get("rows"),
            "complete": complete, "final_exit": rc}
    d = reports_dir / run_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "reverify-sentinel.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (reports_dir / ".last-reverify-run").write_text(run_id + "\n", encoding="utf-8")
    return p


def verify(run_id: str, reports_dir: pathlib.Path | None = None) -> tuple[bool, str]:
    reports_dir = reports_dir or REPORTS
    p = reports_dir / run_id / "reverify-sentinel.json"
    if not p.exists():
        return False, f"哨兵缺失：{p}"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"哨兵不可读：{exc}"
    if d.get("run_id") != run_id:
        return False, f"run_id 不匹配：{d.get('run_id')} != {run_id}"
    if d.get("mode") != "targeted-reverify":
        return False, f"mode 非法：{d.get('mode')}"
    if d.get("settled") != len(EXPECTED_TARGETED) or d.get("expected") != len(EXPECTED_TARGETED):
        return False, f"结算数不符：settled={d.get('settled')} expected={d.get('expected')}"
    for k in ("missing", "extra", "duplicates", "unknown_status"):
        if d.get(k):
            return False, f"{k} 非空：{d.get(k)}"
    counts = {k: int(d.get("counts", {}).get(k, 0)) for k in KNOWN}
    if sum(counts.values()) != d.get("rows") or d.get("rows") != d.get("settled"):
        return False, f"计数和!=行数/结算：sum={sum(counts.values())} rows={d.get('rows')}"
    want = expected_exit(counts, bool(d.get("complete")))
    if d.get("final_exit") != want:
        return False, f"final_exit={d.get('final_exit')} 与政策 {want} 不一致"
    return True, f"OK run_id={run_id} settled={d['settled']} counts={counts} exit={d['final_exit']}"


def main(argv: list[str]) -> int:
    rid = argv[0] if argv else (LAST_RUN_FILE.read_text(encoding="utf-8").strip()
                               if LAST_RUN_FILE.exists() else "")
    if not rid:
        print("REVERIFY_SENTINEL_FAIL: 无 run_id（缺 .last-reverify-run）", file=sys.stderr)
        return 1
    ok, msg = verify(rid)
    print(("REVERIFY_SENTINEL_OK " if ok else "REVERIFY_SENTINEL_FAIL ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
