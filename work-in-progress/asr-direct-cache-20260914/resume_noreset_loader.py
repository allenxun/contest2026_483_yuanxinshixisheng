#!/usr/bin/env python3
"""Resume after a warm reset corrupted the encoder tail; keep decoder RAM."""

import re
import subprocess
import sys
import time

import serial

import cold_reset_loader as loader


def read_until(port, seconds, pattern=None):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        block = port.read(8192)
        if block:
            data.extend(block)
            sys.stdout.buffer.write(block)
            sys.stdout.flush()
            if pattern and re.search(pattern, data):
                break
    return bytes(data)


def enter_fastboot_with_decoder():
    with serial.Serial(port=None, baudrate=1_500_000, timeout=.02,
                       write_timeout=2) as port:
        port.dtr = False
        port.rts = False
        port.port = "/dev/ttyUSB0"
        port.open()
        port.write(b"\x03\r")
        port.flush()
        prompt = read_until(port, 6, rb"(?:^|\n)=>\s*$")
        if not re.search(rb"(?:^|\n)=>\s*$", prompt):
            raise RuntimeError("U-Boot prompt missing")
        port.reset_input_buffer()
        port.write(b"crc32 90000000 44b0310\r")
        port.flush()
        crc = read_until(port, 12, rb"(?:^|\n)=>\s*$")
        if b"2af64aa7" not in crc.lower():
            raise RuntimeError("decoder CRC was not preserved")
        port.write(b"fastboot usb 1\r")
        port.flush()
        entered = read_until(port, 6)
        if b"Enter fastboot...OK" not in entered:
            raise RuntimeError("Fastboot did not start")
        print("RESUME_NORESET decoder_preserved=1 fastboot_started=1", flush=True)


def main():
    enter_fastboot_with_decoder()
    deadline = time.monotonic() + 12 * 60 * 60
    loader.wait_fastboot(deadline)
    loader.download(loader.TAIL, loader.TAIL_SHA, "encoder-tail-retry")
    loader.run_stage("stage-tail")
    loader.wait_fastboot(deadline)
    return subprocess.run([sys.executable, str(loader.HERE / "load_ssid.py"), "transfer"],
                          cwd=str(loader.HERE)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
