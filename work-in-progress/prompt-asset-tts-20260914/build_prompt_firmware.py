"""Build the RAM-only prompt-asset + online-ASR provisioning firmware."""

import hashlib
import json
import os
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path("/home/swl/openvela")
PROJECT = SDK / "work/velavision-project"
BUILD = SDK / "cmake_out/velavision_prompt_asr2_20260914"
RUNTIME = SDK / "work/tts-arena-fix-20260913/speech-runtime-gated-sharedcache2.arm64.o"
EXPECTED_RUNTIME = "fc88e38f0011901241596d41d6e528fd931e79f5650264bcdf057c4c5e4cbe3b"
EXPECTED = {
    "app/k7sound/k7sound_api.h": "b2996b647d76766d087dc2c5dd12499e719808ccae8ca8be983c6237ac12f77e",
    "app/k7sound/k7sound_main.c": "486bfc63c877053f4ed505d979dc16b75efa14c7fb438900caaf882822642a2b",
    "app/k7sound/pio.c": "1103bdbb5381528aab0a0b08c133c52aa28162bce85dfc3658b2272393278a2e",
    "app/k7sound/pio.h": "9d88b701a76c60dac161f0fb21ada424f1f7679e89e97f0d099b6870f9173109",
    "app/voicelink/CMakeLists.txt": "18daceb9c60bb7e7870b988bfa36ee0ff58587c7d77d0601e1a90e62b2b1ab67",
    "app/voicelink/src/k7voice_main.cpp": "ca15536246723a25e2ef1006ee5c36d92876c0b96ad57c489a96723ed1b65018",
    "app/voicelink/src/prompt_asset_output.hpp": "6c1f0fedcd97bc769dbcf933f1ad5a18072b724dd3bc7ee62dab8cc6fe923513",
    "app/voicelink/src/generated/k7_prompt_assets_generated.hpp": "01ccb5aa2aba4df7b03bb2a42965d85c007f58ef594d37ced4a80dd3981633d0",
    "app/voicelink/src/generated/k7_prompt_assets_manifest.json": "92cc72351ef8aa16a8c3dbbdef59e6db38f38ea6130de2868cbf9392f2f3cb0e",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if sha(RUNTIME) != EXPECTED_RUNTIME:
    raise RuntimeError("ASR runtime hash changed")
for relative, expected in EXPECTED.items():
    if sha(PROJECT / relative) != expected:
        raise RuntimeError("formal source changed: " + relative)
if BUILD.exists():
    raise RuntimeError("immutable build directory already exists")

environment = os.environ.copy()
environment["PATH"] = ":".join(str(SDK / item) for item in [
    "prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin",
    "prebuilts/tools/python/bin",
    "prebuilts/build-tools/linux-x86_64/bin",
]) + ":" + environment.get("PATH", "")
environment["PYTHONPATH"] = str(SDK / "prebuilts/tools/python/dist-packages/kconfiglib") + ":" + environment.get("PYTHONPATH", "")

configure = [
    "cmake", "-S", "nuttx", "-B", str(BUILD), "-G", "Ninja",
    "-DBOARD_CONFIG=kickpi_k7:velavision_spoken_tts_local",
    "-DK7VOICE_NATIVE_ORT_ADD=ON",
    "-DK7VOICE_NATIVE_ASR_MODEL=ON",
    "-DK7VOICE_NATIVE_ASR_MIC=ON",
    "-DK7VOICE_PROMPT_ASSETS=ON",
    "-DK7VOICE_NATIVE_TTS=OFF",
    "-DK7VOICE_ORT_OBJECT=" + str(RUNTIME),
    "-DK7VOICE_ORT_OBJECT_SHA256=" + EXPECTED_RUNTIME,
]
record = {
    "runtime_sha256": EXPECTED_RUNTIME,
    "inputs": EXPECTED,
    "runtime_tts_enabled": False,
    "prompt_assets": 20,
    "prompt_speaker_id": 21,
    "prompt_target_peak_ratio": 0.90,
    "codec_dac_attenuation_db": 0,
    "board_tested": False,
}
for phase, command in (("configure", configure),
                       ("build", ["cmake", "--build", str(BUILD), "-j4"])):
    log_path = HERE / ("prompt2-" + phase + ".log")
    with log_path.open("xb") as log:
        result = subprocess.run(command, cwd=str(SDK), env=environment,
                                stdout=log, stderr=subprocess.STDOUT,
                                timeout=2400)
    record[phase + "_exit_code"] = result.returncode
    (HERE / "prompt2-firmware-result.json").write_text(json.dumps(record, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError(phase + " failed; inspect " + str(log_path))

record["artifacts"] = {
    name: {"bytes": (BUILD / name).stat().st_size,
           "sha256": sha(BUILD / name)}
    for name in ("nuttx", "nuttx.bin", ".config")
}
(HERE / "prompt2-firmware-result.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record["artifacts"], indent=2))
