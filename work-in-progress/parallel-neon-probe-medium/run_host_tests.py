"""Run only portable reference C on host, never target/SDK/hardware."""
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

commands = [
    ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
     str(ROOT / "test_reference.c"), "-o", str(ROOT / "reference-test.exe")],
    [str(ROOT / "reference-test.exe")],
]
results = []
for command in commands:
    p = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, timeout=10, cwd=str(ROOT))
    results.append(dict(command=command, returncode=p.returncode,
                        stdout=p.stdout, stderr=p.stderr))
    if p.returncode:
        break
report = dict(scope="host portable reference only; ARM source not compiled or executed",
              passed=len(results) == 2 and all(r["returncode"] == 0 for r in results),
              results=results)
(ROOT / "host-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
inputs = ["README.md", "project-manifest.json", "docs/代码日志对应表.md", "app/k7load/k7load_main.c"]
manifest = dict(inputs={name: sha(PROJECT / name) for name in inputs},
                workspace_instructions={"../AGENTS.md": sha(PROJECT.parent / "AGENTS.md")},
                outputs={p.name: sha(p) for p in sorted(ROOT.iterdir())
                         if p.is_file() and p.name != "hashes.json"})
(ROOT / "hashes.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
