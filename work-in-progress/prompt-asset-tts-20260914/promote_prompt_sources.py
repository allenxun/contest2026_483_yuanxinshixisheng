"""Hash-guarded promotion into the Ubuntu project copy and SDK."""

import hashlib
import os
from pathlib import Path


STAGE = Path("/tmp/k7-prompt-sync/sync-payload")
PROJECT = Path("/home/swl/openvela/work/velavision-project")
SDK = Path("/home/swl/openvela")

FILES = {
    "app/k7sound/k7sound_api.h": (
        "b639422d06913870df9092500f82edd51f04b16b91e9bed291410db8a7395785",
        "b2996b647d76766d087dc2c5dd12499e719808ccae8ca8be983c6237ac12f77e"),
    "app/k7sound/k7sound_main.c": (
        "48eb02cee4f5dd21bd9c79a92de158361c494c51ac97041f807f8e73ad8d2aac",
        "486bfc63c877053f4ed505d979dc16b75efa14c7fb438900caaf882822642a2b"),
    "app/k7sound/pio.c": (
        "ab6a17f53e4f89a2d6f6c15a5497675515b35f2101f4bbacbd354380d8d7d780",
        "1103bdbb5381528aab0a0b08c133c52aa28162bce85dfc3658b2272393278a2e"),
    "app/k7sound/pio.h": (
        "5f25d269159a2a4a9aa55dfa7d7994078058638ebf7788a8f06cc88b3c8b4eba",
        "9d88b701a76c60dac161f0fb21ada424f1f7679e89e97f0d099b6870f9173109"),
    "app/voicelink/CMakeLists.txt": (
        "50d61ae31645152d0c9837f7a21f7720f90e8c2feebd7c187d046851c04b569b",
        "18daceb9c60bb7e7870b988bfa36ee0ff58587c7d77d0601e1a90e62b2b1ab67"),
    "app/voicelink/src/k7voice_main.cpp": (
        "e70022cbb53ad0c4720b2e84c1a9deb89c4bca0cfb491d991774ef3d8eaed00e",
        "ca15536246723a25e2ef1006ee5c36d92876c0b96ad57c489a96723ed1b65018"),
    "app/voicelink/src/prompt_asset_output.hpp": (
        "0ed8d0b504ebada70ff1fb801b8788b1ad678f054f33bcbf5baa52677f82d6f7",
        "6c1f0fedcd97bc769dbcf933f1ad5a18072b724dd3bc7ee62dab8cc6fe923513"),
    "app/voicelink/src/generated/k7_prompt_assets_generated.hpp": (
        "618f88fba748ea72d0ba03defa94a8b192b367de5b4d65126f14f997c8f8d962",
        "01ccb5aa2aba4df7b03bb2a42965d85c007f58ef594d37ced4a80dd3981633d0"),
    "app/voicelink/src/generated/k7_prompt_assets_manifest.json": (
        "103697bbe05e725d60ea440446807933604af64273c718009aefc6d516a7221c",
        "92cc72351ef8aa16a8c3dbbdef59e6db38f38ea6130de2868cbf9392f2f3cb0e"),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sdk_path(relative):
    if not relative.startswith("app/"):
        raise RuntimeError("unexpected source mapping")
    return SDK / "apps/examples" / relative[len("app/"):]


def validate_destination(path, previous, new):
    if path.exists():
        actual = sha(path)
        if actual == new:
            return False
        if previous is None or actual != previous:
            raise RuntimeError("unknown destination change: %s %s" % (path, actual))
    elif previous is not None:
        raise RuntimeError("expected destination missing: " + str(path))
    return True


for relative, (previous, new) in FILES.items():
    source = STAGE / relative
    if not source.is_file() or sha(source) != new:
        raise RuntimeError("staged source hash mismatch: " + relative)
    destinations = (PROJECT / relative, sdk_path(relative))
    decisions = [validate_destination(path, previous, new) for path in destinations]
    for path, update in zip(destinations, decisions):
        if not update:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".prompt-new")
        temporary.write_bytes(source.read_bytes())
        if sha(temporary) != new:
            raise RuntimeError("temporary hash mismatch: " + str(path))
        os.replace(str(temporary), str(path))

for relative, (_previous, new) in FILES.items():
    for path in (PROJECT / relative, sdk_path(relative)):
        if sha(path) != new:
            raise RuntimeError("post-promotion mismatch: " + str(path))
print("promoted=%d destinations=%d" % (len(FILES), 2 * len(FILES)))
