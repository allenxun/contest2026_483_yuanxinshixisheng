#!/usr/bin/env python3
"""Build a one-shot RAM-only encoder-tail + TTS ROMFS + firmware package."""

import hashlib
import json
import zlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
TAIL_CONTAINER = Path("/home/swl/openvela/work/native-asr-model-session/encoder1/encoder-part2-firmware.bin")
TAIL_CONTAINER_SHA = "b09cb375894244cda6c52c67b54dc64befdc771d21dce98ba09abcb80c5514f8"
TAIL_OFFSET = 0x1000000
TAIL_BYTES = 0x3E7DA30
TAIL_CRC = "b5f7ae2d"
TTS = Path("/home/swl/openvela/work/parallel-offline-tts-20260913/k7tts.romfs")
TTS_SHA = "8b30719c6a7d1b424676bb1b6ea950b1dfdeeeb0601531c8e49742d0387a7c0f"
TTS_BYTES = 0x1FB2400
TTS_CRC = "9efc1996"
FIRMWARE = Path("/home/swl/openvela/cmake_out/velavision_prompt_asr_direct_ssid_20260914/nuttx.bin")
FIRMWARE_SHA = "26b95e41ca31460d8e2c9130d1daffbde9426a31b62027072c184fa7076f8992"
FIRMWARE_BYTES = 0xFC3690
FIRMWARE_CRC = "8024e62c"
OUTPUT = HERE / "tail-tts-firmware-oneshot.bin"
MANIFEST = HERE / "tail-tts-firmware-oneshot.json"
MAX_BYTES = 0x07000000


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def append_range(source, target, offset, size):
    source.seek(offset)
    remaining = size
    while remaining:
        block = source.read(min(1024 * 1024, remaining))
        if not block:
            raise RuntimeError("unexpected end of source")
        target.write(block)
        remaining -= len(block)


def main():
    if sha(TAIL_CONTAINER) != TAIL_CONTAINER_SHA:
        raise RuntimeError("tail container SHA mismatch")
    if sha(TTS) != TTS_SHA or TTS.stat().st_size != TTS_BYTES:
        raise RuntimeError("TTS ROMFS mismatch")
    if sha(FIRMWARE) != FIRMWARE_SHA or FIRMWARE.stat().st_size != FIRMWARE_BYTES:
        raise RuntimeError("firmware mismatch")

    with OUTPUT.open("wb") as out, TAIL_CONTAINER.open("rb") as tail:
        append_range(tail, out, TAIL_OFFSET, TAIL_BYTES)
        with TTS.open("rb") as tts:
            append_range(tts, out, 0, TTS_BYTES)
        with FIRMWARE.open("rb") as firmware:
            append_range(firmware, out, 0, FIRMWARE_BYTES)

    payload = OUTPUT.read_bytes()
    if len(payload) > MAX_BYTES:
        raise RuntimeError("package exceeds audited Fastboot buffer")
    if format(zlib.crc32(payload[:TAIL_BYTES]) & 0xffffffff, "08x") != TAIL_CRC:
        raise RuntimeError("tail CRC mismatch")
    tts_start = TAIL_BYTES
    if format(zlib.crc32(payload[tts_start:tts_start + TTS_BYTES]) & 0xffffffff, "08x") != TTS_CRC:
        raise RuntimeError("TTS CRC mismatch")
    firmware_start = tts_start + TTS_BYTES
    if format(zlib.crc32(payload[firmware_start:]) & 0xffffffff, "08x") != FIRMWARE_CRC:
        raise RuntimeError("firmware CRC mismatch")
    result = {
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "crc32": format(zlib.crc32(payload) & 0xffffffff, "08x"),
        "max_bytes": MAX_BYTES,
        "headroom_bytes": MAX_BYTES - len(payload),
        "tail": {"offset": 0, "bytes": TAIL_BYTES, "crc32": TAIL_CRC},
        "tts": {"offset": tts_start, "bytes": TTS_BYTES, "crc32": TTS_CRC},
        "firmware": {"offset": firmware_start, "bytes": FIRMWARE_BYTES, "crc32": FIRMWARE_CRC},
        "flash_commands": False,
        "emmc_written": False,
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
