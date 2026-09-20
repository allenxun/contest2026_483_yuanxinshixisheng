"""Continuously catch a physical RESET, then run the audited RAM-only loader."""

import re
import subprocess
import sys
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
HELPER = Path("/home/swl/openvela/work/velavision-project/work-in-progress/tts-spoken-flow-20260913/load_prefix.py")
LOG = HERE / "catch-reset-20260914.log"


def main():
    output = bytearray()
    with LOG.open("ab") as log, serial.Serial(
        port=None, baudrate=1_500_000, timeout=.02, write_timeout=2,
    ) as port:
        port.dtr = False
        port.rts = False
        port.port = "/dev/ttyUSB0"
        port.open()
        port.reset_input_buffer()
        print("CATCH_RESET armed", flush=True)
        deadline = time.monotonic() + 12 * 60 * 60
        interrupt_at = 0.0
        while time.monotonic() < deadline:
            block = port.read(8192)
            if block:
                output.extend(block)
                if len(output) > 131072:
                    del output[:-65536]
                log.write(block)
                log.flush()
                sys.stdout.buffer.write(block)
                sys.stdout.flush()
            if (b"U-Boot 2017" in output or b"Hit key to stop autoboot" in output) and \
                    time.monotonic() - interrupt_at >= .05:
                port.write(b"\x03")
                port.flush()
                interrupt_at = time.monotonic()
            if re.search(rb"(?:^|\n)=>\s*$", output):
                break
        else:
            return 124

    print("CATCH_RESET uboot_ready=1", flush=True)
    entered = subprocess.run([sys.executable, str(HELPER), "uboot-enter"],
                             cwd=str(HERE)).returncode
    if entered:
        return entered
    print("CATCH_RESET fastboot_started=1", flush=True)
    deadline = time.monotonic() + 12 * 60 * 60
    while time.monotonic() < deadline:
        found = subprocess.run(["lsusb"], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=10)
        if found.returncode == 0 and "18d1:4d00" in found.stdout.lower():
            break
        time.sleep(2)
    else:
        return 124
    time.sleep(1)
    return subprocess.run([sys.executable, str(HERE / "load_ssid.py"), "transfer"],
                          cwd=str(HERE)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
