"""Hash-guard the +24 dB speech source into the guest project and SDK."""

import hashlib
import shutil
from pathlib import Path


EXPECTED_OLD = "7bed3306139af1ea6c15ec6c6c8da52472e231c2a672bb8aab3ff78c1f0b0456"
EXPECTED_NEW = "48eb02cee4f5dd21bd9c79a92de158361c494c51ac97041f807f8e73ad8d2aac"
INCOMING = Path("/tmp/k7sound_main_sharedcache2.c")
TARGETS = [
    Path("/home/swl/openvela/work/velavision-project/app/k7sound/k7sound_main.c"),
    Path("/home/swl/openvela/apps/examples/k7sound/k7sound_main.c"),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if sha(INCOMING) != EXPECTED_NEW:
    raise RuntimeError("incoming +24 dB source hash mismatch")
for target in TARGETS:
    current = sha(target)
    if current not in (EXPECTED_OLD, EXPECTED_NEW):
        raise RuntimeError(f"unknown target change: {target}: {current}")
for target in TARGETS:
    if sha(target) == EXPECTED_OLD:
        shutil.copyfile(INCOMING, target)
    if sha(target) != EXPECTED_NEW:
        raise RuntimeError(f"promotion failed: {target}")
print("promoted_hash=" + EXPECTED_NEW)
