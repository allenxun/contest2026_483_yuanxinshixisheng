"""Build the RAM-only prompt-asset + online-ASR provisioning firmware."""

import hashlib
import json
import os
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path("/home/swl/openvela")
PROJECT = SDK / "work/velavision-project"
BUILD = SDK / "cmake_out/velavision_prompt_asr_direct_ssid_20260914"
RUNTIME = HERE / "speech-runtime-asr-direct-clean-tls.arm64.o"
EXPECTED_RUNTIME = "e3de3502956bbfbd2343472f2bffc0cf841fdf78620af7b60f5d63f28448cf10"
EXPECTED = {
    "app/k7sound/k7sound_api.h": "b2996b647d76766d087dc2c5dd12499e719808ccae8ca8be983c6237ac12f77e",
    "app/k7sound/k7sound_main.c": "486bfc63c877053f4ed505d979dc16b75efa14c7fb438900caaf882822642a2b",
    "app/k7sound/pio.c": "1103bdbb5381528aab0a0b08c133c52aa28162bce85dfc3658b2272393278a2e",
    "app/k7sound/pio.h": "9d88b701a76c60dac161f0fb21ada424f1f7679e89e97f0d099b6870f9173109",
    "app/voicelink/CMakeLists.txt": "18daceb9c60bb7e7870b988bfa36ee0ff58587c7d77d0601e1a90e62b2b1ab67",
    "app/voicelink/src/k7voice_main.cpp": "41768df52e5c3726fa7a4ccf5c745c6531a648bb7f078f395d5a18933554a239",
    "app/voicelink/src/core.cpp": "d83e1df93a0407933914e7514d02ef2ae51314dc2e63f01bcdf73d5efc38ce5a",
    "app/voicelink/include/voicelink/types.hpp": "0bf5d131c7744a74bbd8eedd65d4da6ea89be015f4c165d04dbf47e5d5399002",
    "app/voicelink/include/voicelink/asr_runtime.h": "deb2f2639e27d366420448a973ad47c0048dd7c087ef54ab17ed0b3b29298857",
    "app/voicelink/src/prompt_asset_output.hpp": "92d54469b0afb2243304f7befe0782bbb4a0ad2026659b3658f6cdb6f971484a",
    "app/voicelink/src/generated/k7_prompt_assets_generated.hpp": "50a015f39a2dee0ae785874831a58bab51e0013ff7a187dda9bbe638793eff3a",
    "app/voicelink/src/generated/k7_prompt_assets_manifest.json": "8383cb4596fc3fe2197a5dff94bf67b03158610edcfa3229ccb617abb273393d",
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
    "prompt_assets": 58,
    "prompt_pcm_seconds": 36.775,
    "dynamic_ascii_ssid_spelling": True,
    "prompt_speaker_id": 21,
    "prompt_target_peak_ratio": 0.90,
    "codec_dac_attenuation_db": 0,
    "board_tested": False,
}
for phase, command in (("configure", configure),
                       ("build", ["cmake", "--build", str(BUILD), "-j4"])):
    log_path = HERE / ("direct-ssid-" + phase + ".log")
    with log_path.open("xb") as log:
        result = subprocess.run(command, cwd=str(SDK), env=environment,
                                stdout=log, stderr=subprocess.STDOUT,
                                timeout=2400)
    record[phase + "_exit_code"] = result.returncode
    (HERE / "firmware-result-ssid.json").write_text(json.dumps(record, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError(phase + " failed; inspect " + str(log_path))

record["artifacts"] = {
    name: {"bytes": (BUILD / name).stat().st_size,
           "sha256": sha(BUILD / name)}
    for name in ("nuttx", "nuttx.bin", ".config")
}
(HERE / "firmware-result-ssid.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record["artifacts"], indent=2))
