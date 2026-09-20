import hashlib
import json
import pathlib
import shutil
import subprocess
import time
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent
FILES = [ROOT / "include/tool_executor.hpp", ROOT / "src/tool_executor.cpp", ROOT / "tests/test_tool_executor.cpp"]

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    compiler = shutil.which("g++")
    if not compiler:
        raise SystemExit("g++ not found")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    outdir = ROOT / "evidence" / stamp
    outdir.mkdir(parents=True)
    result = {"schema": 1, "host_only": True, "hardware_tested": False, "runs": [], "source_sha256": {str(p.relative_to(ROOT)).replace('\\', '/'): sha256(p) for p in FILES}}
    for opt in ("O0", "O2"):
        exe = outdir / f"test-{opt}.exe"
        command = [compiler, "-std=c++17", f"-{opt}", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I", str(ROOT / "include"), str(ROOT / "src/tool_executor.cpp"), str(ROOT / "tests/test_tool_executor.cpp"), "-o", str(exe)]
        started = time.monotonic()
        build = subprocess.run(command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        (outdir / f"build-{opt}.stdout.bin").write_bytes(build.stdout)
        (outdir / f"build-{opt}.stderr.bin").write_bytes(build.stderr)
        run = None
        if build.returncode == 0:
            run = subprocess.run([str(exe)], cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            (outdir / f"run-{opt}.stdout.bin").write_bytes(run.stdout)
            (outdir / f"run-{opt}.stderr.bin").write_bytes(run.stderr)
        result["runs"].append({"optimization": opt, "argv": command, "build_exit_code": build.returncode, "run_exit_code": None if run is None else run.returncode, "elapsed_seconds": round(time.monotonic() - started, 6), "executable_sha256": sha256(exe) if exe.exists() else None})
    result["passed"] = all(x["build_exit_code"] == 0 and x["run_exit_code"] == 0 for x in result["runs"])
    (outdir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(outdir)
    print(json.dumps({"passed": result["passed"], "runs": result["runs"]}, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)

if __name__ == "__main__":
    main()
