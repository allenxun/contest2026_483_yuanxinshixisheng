"""Create and audit one bounded OTG payload for prompt-ASR firmware."""

import hashlib
import json
import subprocess
import zlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
BUILD = Path("/home/swl/openvela/cmake_out/velavision_prompt_asr_direct_ssid_20260914")
PREFIX = Path("/home/swl/openvela/work/native-asr-model-session/encoder1/encoder-first-firmware.bin")
FIRMWARE_RESULT = HERE / "firmware-result-ssid.json"
PAYLOAD = HERE / "prompt-asr-direct-ssid-prefix.bin"
MANIFEST = HERE / "ssid-prefix-package.json"
MAX_BYTES = 0x07000000
PREFIX_BYTES = 0x06000000
EXPECTED_PREFIX_SHA256 = "9951c2742be81d6fad8ed3a432c2d294271748f2cfcbb9241235bc8369f5071b"
NM = Path("/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-nm")


def sha(data):
    return hashlib.sha256(data).hexdigest()


result = json.loads(FIRMWARE_RESULT.read_text())
firmware = (BUILD / "nuttx.bin").read_bytes()
prefix = PREFIX.read_bytes()
if sha(firmware) != result["artifacts"]["nuttx.bin"]["sha256"]:
    raise RuntimeError("firmware hash changed")
if sha(prefix) != EXPECTED_PREFIX_SHA256:
    raise RuntimeError("encoder prefix hash changed")
payload = prefix[:PREFIX_BYTES] + firmware
if len(payload) > MAX_BYTES:
    raise RuntimeError("payload exceeds audited U-Boot download buffer")
if MAX_BYTES - len(payload) < 0:
    raise RuntimeError("negative payload headroom")

elf = BUILD / "nuttx"
symbols = subprocess.check_output([str(NM), "-g", "--defined-only", str(elf)], text=True)
required = ("k7_asr_microphone_text", "k7_asr_runtime_reset",
            "k7sound_speak_mono16", "pio_play_mono16")
missing = [name for name in required if symbols.count(" " + name + "\n") != 1]
if missing:
    raise RuntimeError("missing or duplicate final symbols: " + ",".join(missing))

PAYLOAD.write_bytes(payload)
record = {
    "bytes": len(payload),
    "maximum_bytes": MAX_BYTES,
    "headroom_bytes": MAX_BYTES - len(payload),
    "sha256": sha(payload),
    "crc32": "%08x" % (zlib.crc32(payload) & 0xffffffff),
    "firmware_bytes": len(firmware),
    "firmware_sha256": sha(firmware),
    "firmware_crc32": "%08x" % (zlib.crc32(firmware) & 0xffffffff),
    "encoder_prefix_bytes": PREFIX_BYTES,
    "encoder_prefix_source_sha256": sha(prefix),
    "runtime_tts_enabled": False,
    "prompt_assets": 58,
    "prompt_pcm_seconds": 36.775,
    "dynamic_ascii_ssid_spelling": True,
    "prompt_target_peak_ratio": 0.90,
    "codec_dac_attenuation_db": 0,
    "required_final_symbols": list(required),
    "flash_commands": False,
    "emmc_written": False,
    "board_tested": False,
}
MANIFEST.write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
