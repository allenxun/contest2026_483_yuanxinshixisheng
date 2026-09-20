#!/usr/bin/env python3
"""Recover a silent K7 console into U-Boot without writing persistent storage."""

import re
import sys
import time
from pathlib import Path

import serial


PORT = "/dev/ttyUSB0"
LOG = Path(__file__).with_name("recover-console-20260914.log")


def main() -> int:
    output = bytearray()
    with LOG.open("ab") as log, serial.Serial(
        port=None,
        baudrate=1_500_000,
        timeout=0.02,
        write_timeout=2,
    ) as port:
        port.dtr = False
        port.rts = False
        port.port = PORT
        port.open()
        port.reset_input_buffer()

        # Ctrl-C works at either an NSH command line or a U-Boot command line.
        port.write(b"\x03\r")
        port.flush()
        probe_deadline = time.monotonic() + 2
        while time.monotonic() < probe_deadline:
            block = port.read(4096)
            if block:
                output.extend(block)
                log.write(block)
                log.flush()

        # `reboot` is valid in both NSH and U-Boot. It is deliberately the only
        # state-changing command in this recovery helper.
        port.write(b"reboot\r")
        port.flush()
        deadline = time.monotonic() + 28
        last_interrupt = 0.0
        while time.monotonic() < deadline:
            block = port.read(4096)
            if block:
                output.extend(block)
                log.write(block)
                log.flush()
            now = time.monotonic()
            if b"U-Boot 2017" in output or now - last_interrupt >= 0.20:
                port.write(b"\x03")
                port.flush()
                last_interrupt = now
            if re.search(rb"(?:^|\n)=>\s*$", output):
                break

        sys.stdout.buffer.write(output[-16000:])
        sys.stdout.flush()
        if re.search(rb"(?:^|\n)=>\s*$", output):
            print("\nRECOVER_CONSOLE uboot_ready=1")
            return 0
        print("\nRECOVER_CONSOLE uboot_ready=0")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
