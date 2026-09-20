"""Leave a failed Fastboot session at U-Boot after validating staged RAM."""

import re
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
LOG = (HERE / ("otg-hold-" + time.strftime("%Y%m%d-%H%M%S") + ".log")).open("xb")


def read(port, seconds, pattern=None):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data.extend(port.read(4096))
        if pattern and re.search(pattern, data):
            break
    LOG.write(data)
    LOG.flush()
    print(data.decode(errors="replace"), end="", flush=True)
    return bytes(data)


try:
    with serial.Serial("/dev/ttyUSB0", 1500000, timeout=.02,
                       write_timeout=2, rtscts=False, dsrdtr=False,
                       xonxoff=False) as port:
        port.dtr = False
        port.rts = False
        port.write(b"\x03\r")
        port.flush()
        output = read(port, 5, rb"(?:^|\n)=>\s*$")
        if not re.search(rb"(?:^|\n)=>\s*$", output):
            raise RuntimeError("U-Boot prompt missing")
        port.write(b"crc32 90000000 44b0310\r")
        port.flush()
        output = read(port, 30, rb"(?:^|\n)=>\s*$")
        if not re.search(rb"==>\s+2af64aa7\b", output):
            raise RuntimeError("staged decoder CRC mismatch")
        print("OTG_UNPLUG_WINDOW_READY", flush=True)
finally:
    LOG.close()
    print("K7_LOG=" + str(LOG.name), flush=True)
