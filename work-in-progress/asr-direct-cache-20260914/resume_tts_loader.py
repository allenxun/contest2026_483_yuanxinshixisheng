#!/usr/bin/env python3
"""Stash the validated final payload, restore TTS ROMFS, then boot from RAM."""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import serial

import cold_reset_loader as loader


FINAL_BYTES = 0x6FC3690
FINAL_CRC = "1ad383d0"
ENCODER_PREFIX_BYTES = 0x6000000
ENCODER_BYTES = 0x9E7DA30
ENCODER_CRC = "b20f998f"
FIRMWARE_SOURCE = 0x46C00800
FIRMWARE_TARGET = 0x40400000
FIRMWARE_BYTES = 0xFC3690
FIRMWARE_CRC = "8024e62c"
TTS_ROM = Path("/home/swl/openvela/work/parallel-offline-tts-20260913/k7tts.romfs")
TTS_SHA = "8b30719c6a7d1b424676bb1b6ea950b1dfdeeeb0601531c8e49742d0387a7c0f"
TTS_BYTES = 0x1FB2400
TTS_CRC = "9efc1996"
LOG = loader.HERE / "resume-tts-loader-serial-20260914.log"


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


def command(port, text, seconds=20):
    port.write(text.encode("ascii") + b"\r")
    port.flush()
    output = read(port, seconds, rb"(?:^|\n)=>\s*$")
    if not re.search(rb"(?:^|\n)=>\s*$", output):
        raise RuntimeError("U-Boot prompt missing after " + text)
    if b"Unknown command" in output or b"Usage:" in output:
        raise RuntimeError("U-Boot rejected " + text)
    return output


def check_crc(port, address, size, expected):
    output = command(port, f"crc32 {address:x} {size:x}", 35)
    if not re.search(rb"==>\s+" + expected.encode() + rb"\b", output):
        raise RuntimeError(f"CRC mismatch at {address:x}")


def copy(port, source, target, size):
    if not (source + size <= target or target + size <= source):
        raise RuntimeError("overlapping copy refused")
    for offset in range(0, size, 0x400000):
        count = min(0x400000, size - offset)
        command(port, f"cp.b {source + offset:x} {target + offset:x} {count:x}")


def open_port():
    port = serial.Serial("/dev/ttyUSB0", 1_500_000, timeout=.02,
                         write_timeout=2, rtscts=False, dsrdtr=False,
                         xonxoff=False)
    port.dtr = False
    port.rts = False
    return port


def get_prompt(port):
    port.write(b"\x03\r")
    port.flush()
    output = read(port, 6, rb"(?:^|\n)=>\s*$")
    if not re.search(rb"(?:^|\n)=>\s*$", output):
        raise RuntimeError("U-Boot prompt missing")


def stash_final():
    with open_port() as port:
        get_prompt(port)
        check_crc(port, 0x40C00800, FINAL_BYTES, FINAL_CRC)
        check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
        check_crc(port, 0x86000000, 0x3E7DA30, "b5f7ae2d")
        copy(port, 0x40C00800, 0x80000000, ENCODER_PREFIX_BYTES)
        check_crc(port, 0x80000000, ENCODER_BYTES, ENCODER_CRC)
        copy(port, FIRMWARE_SOURCE, FIRMWARE_TARGET, FIRMWARE_BYTES)
        check_crc(port, FIRMWARE_TARGET, FIRMWARE_BYTES, FIRMWARE_CRC)
        port.write(b"fastboot usb 1\r")
        port.flush()
        if b"Enter fastboot...OK" not in read(port, 6):
            raise RuntimeError("Fastboot did not start")
        print("RESUME_TTS final_stashed=1 fastboot_started=1", flush=True)


def boot_stashed():
    with open_port() as port:
        get_prompt(port)
        check_crc(port, 0x80000000, ENCODER_BYTES, ENCODER_CRC)
        check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
        check_crc(port, 0x96000000, TTS_BYTES, TTS_CRC)
        check_crc(port, FIRMWARE_TARGET, FIRMWARE_BYTES, FIRMWARE_CRC)
        if b"edfe0dd0" not in command(port, "md.l 48300000 1").lower():
            raise RuntimeError("DTB magic mismatch")
        port.write(b"booti 40400000 - 48300000\r")
        port.flush()
        output = read(port, 40)
        if b"nsh>" not in output:
            port.write(b"\r")
            port.flush()
            if b"nsh>" not in read(port, 8):
                raise RuntimeError("RAM firmware did not reach NSH")
        print("RESUME_TTS firmware_started=1", flush=True)


def main():
    if TTS_ROM.stat().st_size != TTS_BYTES or loader.digest(TTS_ROM) != TTS_SHA:
        raise RuntimeError("TTS ROMFS input mismatch")
    stash_final()
    deadline = time.monotonic() + 12 * 60 * 60
    loader.wait_fastboot(deadline)
    loader.download(TTS_ROM, TTS_SHA, "tts-romfs")
    env = os.environ.copy()
    env["K7VOICE_PACKAGE_DIR"] = str(loader.HERE)
    if subprocess.run([sys.executable, str(loader.LOADER), "stage-rom-noreset"],
                      cwd=str(loader.HERE), env=env).returncode:
        raise RuntimeError("TTS ROMFS stage failed")
    boot_stashed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
