"""Promote compact prompt assets with exact old/new hash guards."""

import hashlib
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path("/home/swl/openvela/work/velavision-project")
SDK = Path("/home/swl/openvela")
ITEMS = [
    ("prompt_asset_output.hpp", "app/voicelink/src/prompt_asset_output.hpp",
     "6c1f0fedcd97bc769dbcf933f1ad5a18072b724dd3bc7ee62dab8cc6fe923513",
     "aed2dd13205a74fdeba5f6601a122ca7808683eca722e3d5252e52d870d3e7b4"),
    ("k7_prompt_assets_generated.hpp",
     "app/voicelink/src/generated/k7_prompt_assets_generated.hpp",
     "01ccb5aa2aba4df7b03bb2a42965d85c007f58ef594d37ced4a80dd3981633d0",
     "92a5f66e57e4d99f2303b628a7e3df06c4f979cc1ae5d406689fd183ae74957d"),
    ("k7_prompt_assets_manifest.json",
     "app/voicelink/src/generated/k7_prompt_assets_manifest.json",
     "92cc72351ef8aa16a8c3dbbdef59e6db38f38ea6130de2868cbf9392f2f3cb0e",
     "d87690b0834095ed88644c76b41c66e9d22aeeca4d40762514e697ba758d7e1a"),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for filename, relative, old_hash, new_hash in ITEMS:
    source = HERE / filename
    if digest(source) != new_hash:
        raise RuntimeError("staged source hash mismatch: " + filename)
    for destination in (PROJECT / relative,
                        SDK / "apps/examples" / relative.removeprefix("app/")):
        actual = digest(destination)
        if actual not in (old_hash, new_hash):
            raise RuntimeError(f"unknown destination {destination}: {actual}")
        if actual != new_hash:
            temporary = destination.with_name(destination.name + ".compact-new")
            temporary.write_bytes(source.read_bytes())
            if digest(temporary) != new_hash:
                raise RuntimeError("temporary hash mismatch")
            os.replace(temporary, destination)
        print(digest(destination), destination)
