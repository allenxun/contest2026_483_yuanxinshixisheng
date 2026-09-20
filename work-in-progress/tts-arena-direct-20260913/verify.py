import hashlib
import json
import struct
import subprocess
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parents[1]
romfs = root / "work-in-progress/parallel-offline-tts-20260913/k7tts.romfs"
model_offset = 0x730
model_bytes = 31_190_816

raw = romfs.read_bytes()
assert len(raw) == 33_235_968
assert hashlib.sha256(raw).hexdigest() == (
    "8b30719c6a7d1b424676bb1b6ea950b1dfdeeeb0601531c8e49742d0387a7c0f"
)
model = raw[model_offset : model_offset + model_bytes]
assert len(model) == model_bytes
assert hashlib.sha256(model).hexdigest() == (
    "97084af57de4135fc9217851386b1f6d511ae22eba01d9c5d9edf04f0e2adc63"
)

arena_begin = 0x60000000
arena_end = 0x80000000
encoder = (0x80000000, 0x89E7DA30)
decoder = (0x90000000, 0x944B0310)
tts_rom = (0x96000000, 0x97FB2400)
assert arena_end - arena_begin == 512 * 1024 * 1024
assert arena_end <= encoder[0] < encoder[1] <= decoder[0]
assert decoder[1] <= tts_rom[0] < tts_rom[1] <= 0xA0000000
assert tts_rom[0] + model_offset + model_bytes <= tts_rom[1]

source_root = root / (
    "work-in-progress/native-voice-sources/"
    "sherpa-onnx-26aa2fa93210376a89de3a65a1a4dd320c37f5e9/"
    "sherpa-onnx/csrc"
)
vits = (source_root / "offline-tts-vits-model.cc").read_text()
config = (source_root / "offline-tts-vits-model-config.cc").read_text()
assert "auto buf = ReadFile(config.vits.model);" in vits
assert "Ort::Env env_;" in vits
assert 'if (!FileExists(model))' in config

ort_include = root / (
    "work-in-progress/native-voice-sources/"
    "onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d/"
    "include/onnxruntime/core/session"
)
common = [
    "g++", "-D_stdcall=__stdcall", "-D_Frees_ptr_opt_=", "-std=c++17",
    "-Wall", "-Wextra", "-Werror", "-c",
]
includes = [
    "-I" + str(here),
    "-I" + str(here / "test_include"),
    "-I" + str(root / "work-in-progress/native-asr-recognizer"),
    "-I" + str(ort_include),
]
commands = [
    common + [str(here / "compile_storage.cpp"), "-o",
              str(here / "compile_storage.o")] + includes,
    common + [str(here / "compile_asr_storage.cpp"), "-o",
              str(here / "compile_asr_storage.o")] + includes,
    common + [str(here / "speech_runtime_gate.cpp"), "-o",
              str(here / "speech_runtime_gate.o")] + includes,
]
completed = [
    subprocess.run(command, universal_newlines=True, stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE)
    for command in commands
]
passed = all(item.returncode == 0 for item in completed)
result = {
    "status": "pass" if passed else "fail",
    "romfs_sha256": hashlib.sha256(raw).hexdigest(),
    "model_offset": hex(model_offset),
    "model_bytes": model_bytes,
    "model_sha256": hashlib.sha256(model).hexdigest(),
    "arena": [hex(arena_begin), hex(arena_end)],
    "asr_peak_bytes_previous_board": 468_101_988,
    "asr_headroom_bytes_at_previous_peak": (arena_end - arena_begin) - 468_101_988,
    "compile_commands": commands,
    "compile_exit_codes": [item.returncode for item in completed],
    "stderr": [item.stderr for item in completed],
    "board_tested": False,
}
(here / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
if not passed:
    raise SystemExit(1)
print(json.dumps(result, indent=2))
