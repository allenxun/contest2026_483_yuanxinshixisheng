"""Verify and normalize the archived ASR text bridge build evidence."""

import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
EVIDENCE = PROJECT / "evidence/build/voice-asr-text-20260912"
RAW = json.loads((EVIDENCE / "raw/result.json").read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if RAW["configure_exit_code"] != 0 or RAW["build_exit_code"] != 0:
    raise RuntimeError("remote build did not pass")
for relative, digest in RAW["inputs"].items():
    if sha(PROJECT / relative) != digest:
        raise RuntimeError("formal source changed after build: " + relative)
for name, record in RAW["artifacts"].items():
    artifact = EVIDENCE / "artifacts" / name
    if artifact.stat().st_size != record["bytes"] or sha(artifact) != record["sha256"]:
        raise RuntimeError("archived artifact mismatch: " + name)

report = {
    "revision": "voice-asr-text-20260912",
    "configure_exit_code": RAW["configure_exit_code"],
    "build_exit_code": RAW["build_exit_code"],
    "runtime_sha256": RAW["runtime_sha256"],
    "sources": RAW["inputs"],
    "support_inputs": RAW["support_inputs"],
    "artifacts": RAW["artifacts"],
    "elf_symbols_checked": [
        "k7_asr_microphone_text",
        "k7_asr_microphone_probe",
        "k7voice_main",
        "voicelink::Controller::ingest",
        "__emutls_get_address",
    ],
    "ram_only": True,
    "board_tested": False,
}
(EVIDENCE / "verification.json").write_text(
    json.dumps(report, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(report, indent=2))
