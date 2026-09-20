"""Promote the two build-facing source changes with exact destination guards."""

import hashlib
import shutil
from pathlib import Path


PROJECT = Path("/home/swl/openvela/work/velavision-project")
SDK = Path("/home/swl/openvela")
HERE = Path(__file__).resolve().parent
ITEMS = [
    (
        HERE / "k7voice_main.cpp",
        "ca15536246723a25e2ef1006ee5c36d92876c0b96ad57c489a96723ed1b65018",
        [PROJECT / "app/voicelink/src/k7voice_main.cpp",
         SDK / "apps/examples/voicelink/src/k7voice_main.cpp"],
    ),
    (
        HERE / "asr_runtime.h",
        "83959c52640329bd899ab657cd2e4b5fe0d85b1a7461a69c3f8cab9ffd0203b9",
        [PROJECT / "app/voicelink/include/voicelink/asr_runtime.h",
         SDK / "apps/examples/voicelink/include/voicelink/asr_runtime.h"],
    ),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for source, old_hash, destinations in ITEMS:
    for destination in destinations:
        current = digest(destination)
        if current != old_hash and current != digest(source):
            raise RuntimeError(f"refusing unknown destination {destination}: {current}")
for source, _, destinations in ITEMS:
    for destination in destinations:
        if destination != source:
            shutil.copyfile(source, destination)
        print(digest(destination), destination)
