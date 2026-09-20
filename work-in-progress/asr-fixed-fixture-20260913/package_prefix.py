"""Build the bounded RAM-only encoder-prefix plus voice rule provisioning firmware payload."""

import hashlib
import json
import zlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
FIRMWARE = Path("/home/swl/openvela/cmake_out/velavision_asr_fixed_fixture_20260913/nuttx.bin")
PREFIX = Path("/home/swl/openvela/work/native-asr-model-session/encoder1/encoder-first-firmware.bin")
OUTPUT = HERE / "asr-fixed-fixture-prefix.bin"
REPORT = HERE / "prefix-package.json"

EXPECTED_FIRMWARE = json.loads((HERE / "result.json").read_text(encoding="utf-8-sig"))["artifacts"]["nuttx.bin"]["sha256"]
EXPECTED_PREFIX = "9951c2742be81d6fad8ed3a432c2d294271748f2cfcbb9241235bc8369f5071b"


def digest(data):
    return hashlib.sha256(data).hexdigest()


firmware = FIRMWARE.read_bytes()
prefix = PREFIX.read_bytes()
if digest(firmware) != EXPECTED_FIRMWARE:
    raise RuntimeError("firmware hash changed")
if digest(prefix) != EXPECTED_PREFIX:
    raise RuntimeError("encoder prefix hash changed")
payload = prefix[:0x6000000] + firmware
if len(payload) > 0x07000000:
    raise RuntimeError("payload exceeds audited U-Boot download buffer")
OUTPUT.write_bytes(payload)
record = {
    "bytes": len(payload),
    "sha256": digest(payload),
    "crc32": "%08x" % (zlib.crc32(payload) & 0xffffffff),
    "firmware_bytes": len(firmware),
    "firmware_sha256": digest(firmware),
    "firmware_crc32": "%08x" % (zlib.crc32(firmware) & 0xffffffff),
    "flash_commands": False,
}
REPORT.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))

