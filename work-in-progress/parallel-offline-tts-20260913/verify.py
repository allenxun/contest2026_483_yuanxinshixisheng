import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GXX = Path("D:/software/mingw64/mingw64/bin/g++.exe")
SHERPA = ROOT / "work-in-progress/native-voice-sources/sherpa-onnx-26aa2fa93210376a89de3a65a1a4dd320c37f5e9"
RUNTIME = ROOT / "work-in-progress/parallel-voicelink-runtime/runtime/sherpa-onnx-v1.12.14-win-x64-shared"
ASSETS = ROOT.parent / "语音模块/openvela-voicelink/models/vits-icefall-zh-aishell3"
ORT_MODEL = ROOT / "work-in-progress/native-speech-ort-models1/vits.ort"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(command, name, env=None, timeout=60):
    started = time.monotonic()
    proc = subprocess.run(command, cwd=str(ROOT), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env, timeout=timeout)
    (HERE / (name + ".log")).write_bytes(proc.stdout + proc.stderr)
    return {"name": name, "command": [str(x) for x in command],
            "exit_code": proc.returncode,
            "seconds": round(time.monotonic() - started, 3),
            "log_sha256": sha(HERE / (name + ".log"))}

common = [str(GXX), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
          "-I" + str(HERE / "include"), "-I" + str(SHERPA),
          str(HERE / "native_tts_runtime.cpp")]
runs = []
for opt in ("-O0", "-O2"):
    exe = HERE / ("test-contract-" + opt[1:] + ".exe")
    runs.append(run(common + [opt, str(HERE / "test_contract.cpp"), "-o", str(exe)],
                    "compile-contract-" + opt[1:]))
    if runs[-1]["exit_code"] == 0:
        runs.append(run([str(exe)], "run-contract-" + opt[1:]))

real_exe = HERE / "test-real.exe"
import_lib = RUNTIME / "lib/sherpa-onnx-c-api.lib"
runs.append(run(common + ["-O2", str(HERE / "test_real.cpp"), str(import_lib),
                          "-o", str(real_exe)], "compile-real"))
real_env = os.environ.copy()
real_env["PATH"] = os.pathsep.join([str(RUNTIME / "bin"), str(RUNTIME / "lib"),
                                    str(GXX.parent), real_env.get("PATH", "")])
if runs[-1]["exit_code"] == 0:
    for label, model in (("onnx", ASSETS / "model.onnx"), ("ort", ORT_MODEL)):
        runs.append(run([str(real_exe), str(model), str(ASSETS / "tokens.txt"),
                         str(ASSETS / "lexicon.txt")], "run-real-" + label,
                        env=real_env, timeout=90))

inputs = {}
for path in [HERE / "native_tts_runtime.cpp", HERE / "include/voicelink/tts_runtime.h",
             HERE / "test_contract.cpp", HERE / "test_real.cpp", ASSETS / "model.onnx",
             ASSETS / "tokens.txt", ASSETS / "lexicon.txt", ASSETS / "rule.far", ORT_MODEL,
             ROOT / "app/voicelink/src/native_tts_runtime.cpp",
             ROOT / "app/voicelink/include/voicelink/tts_runtime.h"]:
    inputs[str(path)] = {"bytes": path.stat().st_size, "sha256": sha(path)}

result = {
    "status": "pass" if all(x["exit_code"] == 0 for x in runs) else "fail",
    "host": {"contract_fake_api": "O0 and O2", "real_model_runs": ["ONNX", "ORT"],
             "runs": runs},
    "inputs": inputs,
    "arm64": {"candidate_object_compiled": False, "candidate_linked": False,
              "reason": "Ubuntu build tree was inspected read-only; this scoped task did not write an object there."},
    "device": {"tested": False, "firmware_loaded": False},
    "normalization_boundary": {
        "rule_far_required_for_full_number_date_normalization": True,
        "request_contract_has_rule_fsts_field": False,
        "real_test_text_contains_no_digits_or_dates": True
    }
}
(HERE / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
if result["status"] != "pass":
    raise SystemExit(1)
print("PASS: host fake O0/O2 and real ONNX/ORT generation")
