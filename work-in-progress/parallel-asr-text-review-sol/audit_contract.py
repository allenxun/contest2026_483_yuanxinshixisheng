import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


inputs_path = PROJECT / "work-in-progress/asr-text-bridge-20260912/inputs.json"
expected = json.loads(inputs_path.read_text(encoding="utf-8"))
actual = {name: sha256(PROJECT / name) for name in expected}
cmake = (PROJECT / "app/voicelink/CMakeLists.txt").read_text(encoding="utf-8")
builder = (PROJECT / "work-in-progress/asr-text-bridge-20260912/build.py").read_text(
    encoding="utf-8"
)

report = {
    "input_hashes_match": actual == expected,
    "expected_inputs": expected,
    "actual_inputs": actual,
    "formal_runtime_is_direct_target_source":
        "src/native_asr_runtime.cpp" in cmake.split("nuttx_add_application", 1)[1].split(")", 1)[0],
    "runtime_is_external_object": 'target_sources(apps_k7voice PRIVATE "${K7VOICE_ORT_OBJECT}")' in cmake,
    "external_object_hash_required": "K7VOICE_ORT_OBJECT_SHA256" in cmake,
    "builder_asserts_probe_replacement":
        "if old_probe not in link" in builder or "assert old_probe in" in builder,
    "builder_result_exists":
        (PROJECT / "work-in-progress/asr-text-bridge-20260912/result.json").exists(),
    "formal_build_evidence_exists":
        (PROJECT / "evidence/build/voice-asr-text-20260912").exists(),
}
(HERE / "contract-audit-result.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
