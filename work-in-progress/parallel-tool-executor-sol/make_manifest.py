import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
SKIP = {"delivery.json"}

files = []
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or path.name in SKIP or path.suffix == ".exe":
        continue
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    files.append({"path": rel, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

payload = {
    "schema": 1,
    "scope": "host-only isolated candidate; excludes reproducible exe files and delivery.json self-reference",
    "files": files,
}
(ROOT / "delivery.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("files={}".format(len(files)))
