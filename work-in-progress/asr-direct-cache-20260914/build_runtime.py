"""Replace the ASR model/storage and wrapper in the locked speech runtime."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path("/home/swl/openvela")
ASR = SDK / "work/native-asr-recognizer"
BASE_DIR = SDK / "work/tts-arena-fix-20260913"
BASE = BASE_DIR / "speech-runtime-gated-sharedcache2.arm64.o"
TTS_SOURCE = SDK / "work/native-vits-lexicon-20260911/sherpa"
FIRMWARE_BUILD = SDK / "cmake_out/velavision_prompt_asr2_20260914"
TOOL = SDK / "prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin"
EXPECTED_BASE = "fc88e38f0011901241596d41d6e528fd931e79f5650264bcdf057c4c5e4cbe3b"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log_name, timeout=300):
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout)
    (HERE / log_name).write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f"{log_name} failed with {result.returncode}")


if digest(BASE) != EXPECTED_BASE:
    raise RuntimeError("locked speech runtime base changed")

ar = str(TOOL / "aarch64-none-elf-ar")
nm = str(TOOL / "aarch64-none-elf-nm")
objcopy = str(TOOL / "aarch64-none-elf-objcopy")
ld = str(TOOL / "aarch64-none-elf-ld")

# Rebuild the one Sherpa model member that owns ModelStorage.
record = json.loads((ASR / "compile-attempt2.json").read_text())
model_command = list(record["command"])
model_object = HERE / "online-paraformer-model.cc.o"
model_command[model_command.index("-c") + 1] = str(HERE / "online-paraformer-model.cc")
model_command[model_command.index("-o") + 1] = str(model_object)
rewrites = {
    "-I/dev/shm/velavision-ort-session-20260911/ort/include/onnxruntime/core/session": "-I" + str(HERE),
    "-I/dev/shm/velavision-sherpa-asr-20260911/sherpa": "-I" + str(TTS_SOURCE),
    "-I/dev/shm/velavision_audio_sound_20260910/apps/include": "-I" + str(FIRMWARE_BUILD / "apps/include"),
    "-I/dev/shm/velavision_audio_sound_20260910/include/libcxx": "-I" + str(FIRMWARE_BUILD / "include/libcxx"),
    "-I/dev/shm/velavision_audio_sound_20260910/include/libcxx_config": "-I" + str(FIRMWARE_BUILD / "include/libcxx_config"),
    "-I/dev/shm/velavision_audio_sound_20260910/include/libcxxabi": "-I" + str(FIRMWARE_BUILD / "include/libcxxabi"),
    "/dev/shm/velavision_audio_sound_20260910/include": str(FIRMWARE_BUILD / "include"),
}
model_command = [rewrites.get(item, item) for item in model_command]
model_command[model_command.index("-c"):model_command.index("-c")] = [
    "-I" + str(HERE), "-I" + str(BASE_DIR)]
run(model_command, "compile-model.log")

archive = ASR / "link2/libsherpa-onnx-core.a"
member = "online-paraformer-model.cc.obj"
original_model = HERE / member
original_model.write_bytes(subprocess.check_output([ar, "p", str(archive), member]))


def strong_symbols(path):
    result = []
    for line in subprocess.check_output(
            [nm, "-g", "--defined-only", str(path)], text=True).splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[-2].upper() not in ("U", "W", "V"):
            result.append(fields[-1])
    return sorted(set(result))


model_symbols = strong_symbols(original_model)
model_weakened = HERE / "runtime-model-weakened.o"
shutil.copyfile(BASE, model_weakened)
run([objcopy, *["--weaken-symbol=" + item for item in model_symbols],
     str(model_weakened)], "weaken-model.log")
direct_model = HERE / "runtime-direct-model.o"
run([ld, "-r", "--strip-debug", "-o", str(direct_model),
     str(model_weakened), str(model_object)], "link-model.log")

# Compile the lifecycle-safe cached ASR wrapper with the same locked flags.
compile_record = json.loads((SDK / "work/velavision-project/work-in-progress/voice-ui-connect-20260913/result.json").read_text(encoding="utf-8-sig"))
wrapper_command = list(compile_record["compile"][0]["command"])
wrapper_rewrites = {
    "-I/dev/shm/velavision-ort-session-20260911/ort/include/onnxruntime/core/session": "-I" + str(HERE),
    "-I/dev/shm/velavision-sherpa-asr-20260911/sherpa": "-I" + str(TTS_SOURCE),
    "-I/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/apps/include": "-I" + str(FIRMWARE_BUILD / "apps/include"),
    "-I/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/include/libcxx": "-I" + str(FIRMWARE_BUILD / "include/libcxx"),
    "-I/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/include/libcxx_config": "-I" + str(FIRMWARE_BUILD / "include/libcxx_config"),
    "-I/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/include/libcxxabi": "-I" + str(FIRMWARE_BUILD / "include/libcxxabi"),
    "/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/include": str(FIRMWARE_BUILD / "include"),
}
wrapper_command = [wrapper_rewrites.get(item, item) for item in wrapper_command]
wrapper_command[wrapper_command.index("-c"):wrapper_command.index("-c")] = [
    "-I" + str(HERE), "-I" + str(BASE_DIR)]
wrapper_object = HERE / "native_asr_runtime.cpp.o"
wrapper_command[wrapper_command.index("-c") + 1] = str(HERE / "native_asr_runtime.cpp")
wrapper_command[wrapper_command.index("-o") + 1] = str(wrapper_object)
run(wrapper_command, "compile-wrapper.log")

wrapper_symbols = strong_symbols(wrapper_object)
base_definitions = set(strong_symbols(direct_model))
replace_symbols = sorted(base_definitions.intersection(wrapper_symbols))
wrapper_weakened = HERE / "runtime-wrapper-weakened.o"
shutil.copyfile(direct_model, wrapper_weakened)
run([objcopy, *["--weaken-symbol=" + item for item in replace_symbols],
     str(wrapper_weakened)], "weaken-wrapper.log")
final = HERE / "speech-runtime-asr-direct-cache.arm64.o"
run([ld, "-r", "--strip-debug", "-o", str(final),
     str(wrapper_weakened), str(wrapper_object)], "link-runtime.log")

definitions = strong_symbols(final)
required = ["k7_asr_audio_text", "k7_asr_model_session_probe",
            "k7_asr_microphone_text", "k7_asr_runtime_reset"]
counts = {item: definitions.count(item) for item in required}
result = {
    "status": "pass" if all(value == 1 for value in counts.values()) else "fail",
    "base_sha256": digest(BASE),
    "output_bytes": final.stat().st_size,
    "output_sha256": digest(final),
    "source_sha256": {
        name: digest(HERE / name) for name in (
            "native_asr_runtime.cpp", "native_model_storage.hpp",
            "online-paraformer-model.cc", "shared_runtime.hpp")},
    "model_replaced_symbols": len(model_symbols),
    "wrapper_replaced_symbols": replace_symbols,
    "required_strong_counts": counts,
    "model_command": model_command,
    "wrapper_command": wrapper_command,
    "firmware_linked": False,
    "board_tested": False,
}
(HERE / "runtime-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({key: value for key, value in result.items()
                  if key not in ("model_command", "wrapper_command",
                                 "wrapper_replaced_symbols")}, indent=2))
if result["status"] != "pass":
    raise SystemExit(1)
