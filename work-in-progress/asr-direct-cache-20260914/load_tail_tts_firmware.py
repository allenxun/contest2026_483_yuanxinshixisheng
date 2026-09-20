#!/usr/bin/env python3
"""Download the one-shot recovery package, validate it, and boot from RAM."""

import json
import os
import re
import subprocess
import sys
import time

import serial

import cold_reset_loader as loader


MANIFEST_PATH = loader.HERE / "tail-tts-firmware-oneshot.json"
PAYLOAD = loader.HERE / "tail-tts-firmware-oneshot.bin"
SCRATCH = 0x40C00800
ENCODER_PREFIX_BYTES = 0x6000000
ENCODER_PREFIX_CRC = None
ENCODER_BYTES = 0x9E7DA30
ENCODER_CRC = "b20f998f"
LOG = loader.HERE / "tail-tts-firmware-serial-20260914.log"


def read(port, seconds, pattern=None):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        block = port.read(8192)
        if block:
            data.extend(block)
            with LOG.open("ab") as log:
                log.write(block)
            sys.stdout.buffer.write(block)
            sys.stdout.flush()
            if pattern and re.search(pattern, data):
                break
    return bytes(data)


def command(port, text, seconds=25):
    port.write(text.encode("ascii") + b"\r")
    port.flush()
    output = read(port, seconds, rb"(?:^|\n)=>\s*$")
    if not re.search(rb"(?:^|\n)=>\s*$", output):
        raise RuntimeError("U-Boot prompt missing after " + text)
    if b"Unknown command" in output or b"Usage:" in output:
        raise RuntimeError("U-Boot rejected " + text)
    return output


def check_crc(port, address, size, expected):
    output = command(port, f"crc32 {address:x} {size:x}", 40)
    if not re.search(rb"==>\s+" + expected.encode() + rb"\b", output):
        raise RuntimeError(f"CRC mismatch at {address:x}")


def copy(port, source, target, size):
    if not (source + size <= target or target + size <= source):
        raise RuntimeError("overlapping copy refused")
    for offset in range(0, size, 0x400000):
        count = min(0x400000, size - offset)
        command(port, f"cp.b {source + offset:x} {target + offset:x} {count:x}")


def stage_and_boot(manifest):
    with serial.Serial("/dev/ttyUSB0", 1_500_000, timeout=.02,
                       write_timeout=2, rtscts=False, dsrdtr=False,
                       xonxoff=False) as port:
        port.dtr = False
        port.rts = False
        port.write(b"\x03\r")
        port.flush()
        if not re.search(rb"(?:^|\n)=>\s*$", read(port, 6, rb"(?:^|\n)=>\s*$")):
            raise RuntimeError("U-Boot prompt missing")
        check_crc(port, SCRATCH, manifest["bytes"], manifest["crc32"])
        check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
        tail = manifest["tail"]
        tts = manifest["tts"]
        firmware = manifest["firmware"]
        copy(port, SCRATCH + tail["offset"], 0x86000000, tail["bytes"])
        copy(port, SCRATCH + tts["offset"], 0x96000000, tts["bytes"])
        copy(port, SCRATCH + firmware["offset"], 0x40400000, firmware["bytes"])
        check_crc(port, 0x80000000, ENCODER_BYTES, ENCODER_CRC)
        check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
        check_crc(port, 0x96000000, tts["bytes"], tts["crc32"])
        check_crc(port, 0x40400000, firmware["bytes"], firmware["crc32"])
        if b"edfe0dd0" not in command(port, "md.l 48300000 1").lower():
            raise RuntimeError("DTB magic mismatch")
        port.write(b"booti 40400000 - 48300000\r")
        port.flush()
        output = read(port, 45)
        if b"nsh>" not in output:
            port.write(b"\r")
            port.flush()
            if b"nsh>" not in read(port, 8):
                raise RuntimeError("RAM firmware did not reach NSH")
        print("TAIL_TTS_FIRMWARE firmware_started=1", flush=True)


def main():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if loader.digest(PAYLOAD) != manifest["sha256"]:
        raise RuntimeError("one-shot package SHA mismatch")
    loader.wait_fastboot(time.monotonic() + 12 * 60 * 60)
    result_path = loader.HERE / ("tail-tts-firmware-usb-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(loader.USB_DEPS) + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    command_line = [
        sys.executable, str(loader.DOWNLOADER), str(PAYLOAD), "--sha256", manifest["sha256"],
        "--vid", "0x18d1", "--pid", "0x4d00", "--serial", loader.SERIAL,
        "--audited-running-buffer", loader.MAX_BUFFER, "--result", str(result_path),
    ]
    if subprocess.run(command_line, env=env).returncode:
        raise RuntimeError("one-shot USB download failed")
    stage_and_boot(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
