"""Guarded project-to-SDK sync for the fixed prompt/SSID flow only."""

import hashlib
import json
import shutil
from pathlib import Path


PROJECT = Path("/home/swl/openvela/work/velavision-project")
SDK = Path("/home/swl/openvela/apps/examples/voicelink")
EXPECTED_OLD = {
    "src/k7voice_main.cpp": "904ad0991a59be7051c1f8ec2483d1cdd5c59554cbfcda9edad2f1102e6104a6",
    "src/prompt_asset_output.hpp": "aed2dd13205a74fdeba5f6601a122ca7808683eca722e3d5252e52d870d3e7b4",
    "include/voicelink/types.hpp": "de8e80cc948e5c3d8a8b990a7a9d2fc6f3610528504d8cc20823d95c28527a21",
    "src/generated/k7_prompt_assets_generated.hpp": "92a5f66e57e4d99f2303b628a7e3df06c4f979cc1ae5d406689fd183ae74957d",
    "src/generated/k7_prompt_assets_manifest.json": "d87690b0834095ed88644c76b41c66e9d22aeeca4d40762514e697ba758d7e1a",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


record = {"files": {}, "excluded": ["src/native_asr_runtime.cpp"]}
for relative, old_hash in EXPECTED_OLD.items():
    source = PROJECT / "app/voicelink" / relative
    target = SDK / relative
    new_hash = digest(source)
    current_hash = digest(target)
    if current_hash not in (old_hash, new_hash):
        raise RuntimeError("unknown SDK change: " + str(target))
    if current_hash != new_hash:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(target))
    if digest(target) != new_hash:
        raise RuntimeError("post-copy mismatch: " + str(target))
    record["files"][relative] = {
        "old_sha256": old_hash,
        "new_sha256": new_hash,
        "changed": current_hash != new_hash,
    }

unknown_asr = SDK / "src/native_asr_runtime.cpp"
record["excluded_asr_sha256"] = digest(unknown_asr)
if record["excluded_asr_sha256"] != "4a976bb90e562ac034d81fc7c0a27c01d618086b491808082272b4fc894df93b":
    raise RuntimeError("unexpected excluded ASR source hash")

output = Path(__file__).with_name("sync-prompt-flow-result.json")
output.write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
