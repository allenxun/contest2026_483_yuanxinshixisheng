#!/usr/bin/env python3
import hashlib
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
EVIDENCE = ROOT / "evidence"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command, output_path: pathlib.Path):
    completed = subprocess.run(
        command, cwd=str(PROJECT), universal_newlines=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, encoding="utf-8", errors="replace"
    )
    output_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode:
        print(completed.stdout, end="")
        raise SystemExit(completed.returncode)
    return completed.stdout


def main():
    stamp = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    run_dir = EVIDENCE / stamp
    run_dir.mkdir(parents=True)
    files = [
        ROOT / "include/wifi_transaction_adapter.hpp",
        ROOT / "src/wifi_transaction_adapter.cpp",
        ROOT / "tests/test_wifi_transaction_adapter.cpp",
        ROOT / "INTEGRATION.md",
        ROOT / "HANDOFF.md",
        ROOT / "README.md",
        ROOT / "run_tests.py",
        ROOT / "evidence/inputs.json",
    ]
    builds = []
    for optimization in ("O0", "O2"):
        executable = run_dir / f"test-{optimization}.exe"
        command = [
            "g++", f"-{optimization}", "-std=c++17", "-Wall", "-Wextra",
            "-Werror", "-pedantic", "-I", str(ROOT / "include"),
            "-I", str(PROJECT / "app/voicelink/include"),
            str(ROOT / "src/wifi_transaction_adapter.cpp"),
            str(PROJECT / "app/voicelink/src/core.cpp"),
            str(PROJECT / "app/voicelink/src/parsers.cpp"),
            str(ROOT / "tests/test_wifi_transaction_adapter.cpp"),
            "-o", str(executable),
        ]
        build_output = run(command, run_dir / f"build-{optimization}.raw.txt")
        test_output = run([str(executable)], run_dir / f"test-{optimization}.raw.txt")
        builds.append({
            "optimization": optimization,
            "command": command,
            "build_exit_code": 0,
            "build_output": build_output,
            "test_exit_code": 0,
            "test_output": test_output,
            "executable_sha256": sha256(executable),
        })
    result = {
        "scope": "host fake backend only; no SDK, VM, serial, device, radio or central log access",
        "scenario_groups": 10,
        "passed": True,
        "builds": builds,
        "source_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
                           for path in files},
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"passed": True, "result": str(run_dir / "result.json")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
