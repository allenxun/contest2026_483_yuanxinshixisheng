from __future__ import print_function

import hashlib
import json
import os
from datetime import datetime


ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = set(["out", "__pycache__"])
SKIP_FILES = set(["hashes.json"])


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


files = {}
for base, dirs, names in os.walk(ROOT):
    dirs[:] = sorted([item for item in dirs if item not in SKIP_DIRS])
    for name in sorted(names):
        if name in SKIP_FILES:
            continue
        path = os.path.join(base, name)
        relative = os.path.relpath(path, ROOT).replace(os.sep, "/")
        files[relative] = {
            "bytes": os.path.getsize(path),
            "sha256": digest(path),
        }

result = {
    "artifact": "parallel-https-client-sol",
    "generated_local": datetime.now().astimezone().isoformat(),
    "scope": "all candidate files except generated out/ and hashes.json itself",
    "files": files,
}
with open(os.path.join(ROOT, "hashes.json"), "w") as stream:
    json.dump(result, stream, indent=2, sort_keys=True)
    stream.write("\n")
print("hashed {} files".format(len(files)))
