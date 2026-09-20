"""Capture an already running provisioning command without writing to UART."""

import time
from pathlib import Path

import serial


here = Path(__file__).resolve().parent
stamp = time.strftime("%Y%m%d-%H%M%S")
log = here / ("voice-provision-recovery-" + stamp + ".log")
port = serial.Serial("/dev/ttyUSB0", 1500000, timeout=.02, write_timeout=2,
                     rtscts=False, dsrdtr=False, xonxoff=False)
port.dtr = False
port.rts = False
deadline = time.monotonic() + 420
try:
    with log.open("wb") as output:
        while time.monotonic() < deadline:
            block = port.read(8192)
            if not block:
                continue
            output.write(block)
            output.flush()
            print(block.decode("utf-8", errors="replace"), end="", flush=True)
            if (b"VOICE_PROVISION phase=" in block or
                    b"VOICE_PROVISION timeout" in block or b"nsh>" in block):
                break
finally:
    port.close()
print("\nEVIDENCE=" + str(log), flush=True)
