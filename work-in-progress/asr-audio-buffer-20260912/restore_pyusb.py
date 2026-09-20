"""Restore the pinned PyUSB runtime into tmpfs without pip or root access."""

import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path


VERSION = "1.3.1"
TARGET = Path("/dev/shm/velavision-usb-pydeps-20260912")
METADATA = "https://pypi.org/pypi/pyusb/%s/json" % VERSION


with urllib.request.urlopen(METADATA, timeout=20) as response:
    metadata_bytes = response.read()
metadata = json.loads(metadata_bytes.decode("utf-8"))
sdists = [item for item in metadata["urls"] if item["packagetype"] == "sdist"]
if len(sdists) != 1:
    raise RuntimeError("expected exactly one source distribution")
release = sdists[0]
if release["digests"]["sha256"] == "":
    raise RuntimeError("missing PyPI SHA256")
with urllib.request.urlopen(release["url"], timeout=30) as response:
    archive = response.read()
actual = hashlib.sha256(archive).hexdigest()
if actual != release["digests"]["sha256"]:
    raise RuntimeError("PyUSB source hash mismatch")

with tempfile.TemporaryDirectory(prefix="velavision-pyusb-") as temp_name:
    temp = Path(temp_name)
    archive_path = temp / "pyusb.tar.gz"
    archive_path.write_bytes(archive)
    with tarfile.open(archive_path, "r:gz") as tar:
        root = temp.resolve()
        for member in tar.getmembers():
            target = (temp / member.name).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError("unsafe path in PyUSB source archive")
        tar.extractall(temp)
    candidates = list(temp.glob("pyusb-*/usb"))
    if len(candidates) != 1:
        raise RuntimeError("expected one usb package in source distribution")
    TARGET.mkdir(parents=True, exist_ok=True)
    destination = TARGET / "usb"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(candidates[0], destination)

record = {
    "version": VERSION,
    "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
    "archive_url": release["url"],
    "archive_sha256": actual,
    "target": str(TARGET),
}
(TARGET / "restore.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))
