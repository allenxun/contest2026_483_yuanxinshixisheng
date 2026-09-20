"""Relink ASR from the locked object list with the model archive member replaced."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path("/home/swl/openvela")
ASR = SDK / "work/native-asr-recognizer"
PROJECT = SDK / "work/velavision-project"
TOOL = SDK / "prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin"
SUPPORT = PROJECT / "work-in-progress/voice-rule-provision-20260912/support"
ICONV = PROJECT / "work-in-progress/voice-ui-connect-20260913/libk7_iconv.a"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log_name, timeout=300):
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout)
    (HERE / log_name).write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f"{log_name} failed with {result.returncode}")


ar = str(TOOL / "aarch64-none-elf-ar")
nm = str(TOOL / "aarch64-none-elf-nm")
runtime_record = json.loads((HERE / "runtime-result.json").read_text())

# Recompile the replacement member with the exact previously captured command.
model_object = HERE / "online-paraformer-model.cc.obj"
model_command = list(runtime_record["model_command"])
model_command[model_command.index("-c") + 1] = str(HERE / "online-paraformer-model.cc")
model_command[model_command.index("-o") + 1] = str(model_object)
run(model_command, "clean-compile-model.log")

wrapper_object = HERE / "native_asr_runtime.clean.o"
wrapper_command = list(runtime_record["wrapper_command"])
wrapper_command[wrapper_command.index("-c") + 1] = str(HERE / "native_asr_runtime.cpp")
wrapper_command[wrapper_command.index("-o") + 1] = str(wrapper_object)
run(wrapper_command, "clean-compile-wrapper.log")

extra_objects = []
extra_commands = []
for source_name in ("shared_model_runtime.cpp", "speech_runtime_gate.cpp"):
    command = list(wrapper_command)
    source = HERE / source_name
    output = HERE / (source_name + ".o")
    command[command.index("-c") + 1] = str(source)
    command[command.index("-o") + 1] = str(output)
    run(command, "clean-compile-" + source_name + ".log")
    extra_objects.append(output)
    extra_commands.append(command)

# Replace the archive member before the relocatable link resolves references.
original_archive = ASR / "link2/libsherpa-onnx-core.a"
clean_archive = HERE / "libsherpa-onnx-core-direct.a"
shutil.copyfile(original_archive, clean_archive)
run([ar, "r", str(clean_archive), str(model_object)], "clean-archive-model.log")
members = subprocess.check_output([ar, "t", str(clean_archive)], text=True).splitlines()
if members.count(model_object.name) != 1:
    raise RuntimeError("replacement model archive member is not unique")

prior = json.loads((ASR / "link2/result.json").read_text())
link = list(prior["link_command"])
if link.count("--undefined=SherpaOnnxCreateOfflineTts") != 1:
    raise RuntimeError("unexpected prior TTS pull marker")
link.remove("--undefined=SherpaOnnxCreateOfflineTts")
final = HERE / "speech-runtime-asr-direct-clean.arm64.o"
link[link.index("-o") + 1] = str(final)
replacements = {
    str(ASR / "link2/recognizer_probe.cpp.o"): str(wrapper_object),
    str(original_archive): str(clean_archive),
    "/dev/shm/velavision-native-asr-add-probe-20260911/add_probe.o":
        str(SUPPORT / "add_probe.o"),
    "/dev/shm/velavision-ort-session-20260911/config-attempt9/libk7_iconv.a":
        str(ICONV),
    "/dev/shm/velavision-ort-session-20260911/support-attempt1/libk7_locale.a":
        str(SUPPORT / "libk7_locale.a"),
}
for old, new in replacements.items():
    if link.count(old) != 1 or not Path(new).is_file():
        raise RuntimeError("missing or duplicate locked link input: " + old)
link = [replacements.get(item, item) for item in link]
link[link.index("--end-group"):link.index("--end-group")] = [
    str(item) for item in extra_objects]
run(link, "clean-link-runtime.log", timeout=600)

nm_text = subprocess.check_output([nm, "-g", str(final)], text=True)
required = ("k7_asr_audio_text", "k7_asr_model_session_probe",
            "k7_asr_microphone_text", "k7_asr_runtime_reset",
            "k7_speech_runtime_try_acquire", "k7_speech_runtime_release",
            "SherpaOnnxCreateOnlineRecognizer")
counts = {name: nm_text.count(" T " + name + "\n") for name in required}
strings_text = subprocess.check_output(["strings", str(final)], text=True,
                                       errors="replace")
result = {
    "status": "pass",
    "output_bytes": final.stat().st_size,
    "output_sha256": digest(final),
    "clean_archive_sha256": digest(clean_archive),
    "direct_marker_count": strings_text.count("ASR_STORAGE direct encoder="),
    "legacy_copy_marker_count": strings_text.count("ASR persistent model hash"),
    "tts_entry_count": nm_text.count(" T k7_tts_synthesize\n"),
    "required_strong_counts": counts,
    "source_sha256": {name: digest(HERE / name) for name in (
        "native_asr_runtime.cpp", "native_model_storage.hpp",
        "online-paraformer-model.cc", "shared_model_runtime.cpp",
        "shared_runtime.hpp", "speech_runtime_gate.cpp")},
    "support_sha256": {str(path): digest(path) for path in
                       (SUPPORT / "add_probe.o", SUPPORT / "libk7_locale.a", ICONV)},
    "model_command": model_command,
    "wrapper_command": wrapper_command,
    "extra_commands": extra_commands,
    "link_command": link,
    "firmware_linked": False,
    "board_tested": False,
}
if (any(value != 1 for value in counts.values()) or
        result["direct_marker_count"] != 1 or
        result["legacy_copy_marker_count"] != 0 or
        result["tts_entry_count"] != 0):
    result["status"] = "fail"
(HERE / "clean-runtime-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({key: value for key, value in result.items()
                  if not key.endswith("command") and key != "extra_commands"}, indent=2))
if result["status"] != "pass":
    raise SystemExit(1)
