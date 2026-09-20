#!/usr/bin/env python3
"""Recover a failed second Fastboot enumeration while preserving decoder RAM."""

import re
import sys
import time

import serial


PORT = "/dev/ttyUSB0"
DECODER_CRC = b"2af64aa7"


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


def command(port, text, seconds=8):
    port.reset_input_buffer()
    port.write(text.encode("ascii") + b"\r")
    port.flush()
    return read_until(port, seconds, rb"(?:^|\n)=>\s*$")


def main():
    with serial.Serial(port=None, baudrate=1_500_000, timeout=.02,
                       write_timeout=2) as port:
        port.dtr = False
        port.rts = False
        port.port = PORT
        port.open()

        # Stop the failed Fastboot gadget and recover the U-Boot prompt.
        port.write(b"\x03\r")
        port.flush()
        output = read_until(port, 6, rb"(?:^|\n)=>\s*$")
        if not re.search(rb"(?:^|\n)=>\s*$", output):
            raise RuntimeError("could not exit failed Fastboot")

        before = command(port, "crc32 90000000 44b0310")
        if DECODER_CRC not in before.lower():
            raise RuntimeError("decoder CRC lost before reset")

        port.write(b"reset\r")
        port.flush()
        boot = bytearray()
        deadline = time.monotonic() + 30
        last_interrupt = 0.0
        while time.monotonic() < deadline:
            block = port.read(8192)
            if block:
                boot.extend(block)
                sys.stdout.buffer.write(block)
                sys.stdout.flush()
            now = time.monotonic()
            if (b"U-Boot 2017" in boot or b"Hit key to stop autoboot" in boot) and now - last_interrupt > .05:
                port.write(b"\x03")
                port.flush()
                last_interrupt = now
            if re.search(rb"(?:^|\n)=>\s*$", boot):
                break
        if not re.search(rb"(?:^|\n)=>\s*$", boot):
            raise RuntimeError("autoboot was not interrupted")

        after = command(port, "crc32 90000000 44b0310")
        if DECODER_CRC not in after.lower():
            raise RuntimeError("decoder CRC lost after reset")

        entered = command(port, "fastboot usb 1", 6)
        if b"Enter fastboot...OK" not in entered:
            raise RuntimeError("Fastboot did not restart")
        print("\nRECOVER_SECOND_FASTBOOT decoder_preserved=1 fastboot_started=1", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
