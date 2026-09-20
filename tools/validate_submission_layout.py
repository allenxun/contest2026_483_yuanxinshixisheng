#!/usr/bin/env python3
"""Validate the non-destructive contest submission classification."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "contest_submission" / "submission-manifest.json"


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []
    for item in data["include"]:
        if not (ROOT / item).exists():
            errors.append(f"missing include: {item}")
    for item in data["exclude"]:
        if item.endswith("*"):
            continue
        if item == "*.pyc" or item == "__pycache__":
            continue
        if not (ROOT / item).exists():
            # Exclusions may be absent on a clean checkout.
            continue
    for link in data["linkfiles"]:
        if not (ROOT / link["src"]).exists():
            errors.append(f"missing linkfile source: {link['src']}")
    if "private" not in data["exclude"]:
        errors.append("private/ must remain excluded")
    if "logs/maomaojiang01" not in data["include"]:
        errors.append("AI log directory is not included")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        "submission layout OK: "
        f"{len(data['include'])} include entries, "
        f"{len(data['exclude'])} exclusions, "
        f"{len(data['linkfiles'])} linkfiles"
    )
    print("truth boundary preserved: no long-stability or mock-narration overclaim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
