"""Compile the formal MiMo sources with an existing K7 ARM64 command line."""

import json
import shlex
import subprocess
from pathlib import Path


SDK = Path("/home/swl/openvela")
PROJECT = SDK / "work/velavision-project"
DB = SDK / "cmake_out/velavision_k7cloud_link_attempt5_20260913/compile_commands.json"
FORMAL = PROJECT / "app/k7agent/cloud"
OUT = PROJECT / "work-in-progress/mimo-cloud-client-20260913/arm-out"


def main():
    commands = json.loads(DB.read_text(encoding="utf-8"))
    template = next(item for item in commands
                    if item["file"].endswith("/cloud/src/vv_https_client.c"))
    base = shlex.split(template["command"])
    old_source = template["file"]
    old_include = "-I" + str(SDK / "apps/examples/k7agent/cloud/include")
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name in ("mimo_cloud_client.c", "mimo_v25_profile.c"):
        source = FORMAL / "src" / name
        target = OUT / (name + ".o")
        command = list(base)
        command[command.index(old_source)] = str(source)
        if old_include in command:
            command[command.index(old_include)] = "-I" + str(FORMAL / "include")
        else:
            command.insert(1, "-I" + str(FORMAL / "include"))
        out_index = command.index("-o") + 1
        command[out_index] = str(target)
        completed = subprocess.run(command, cwd=template["directory"],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, check=False)
        log = OUT / (name + ".log")
        log.write_bytes(completed.stdout)
        if completed.returncode:
            raise RuntimeError("ARM compile failed for %s; see %s" % (name, log))
        results.append({"source": str(source), "object": str(target),
                        "bytes": target.stat().st_size,
                        "log_bytes": log.stat().st_size})
    report = {"revision": "mimo-v25-formal-arm-compile-20260913",
              "compile_database": str(DB), "results": results,
              "sdk_modified": False, "network_called": False,
              "credentials_present": False}
    (OUT / "result.json").write_text(json.dumps(report, indent=2) + "\n",
                                      encoding="utf-8")
    print("PASS arm_objects=%d" % len(results))


if __name__ == "__main__":
    main()
