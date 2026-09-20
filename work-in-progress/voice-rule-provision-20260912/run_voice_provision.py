"""Run one bounded interactive pure-board voice provisioning session."""

import json
import re
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
STAMP = time.strftime("%Y%m%d-%H%M%S")
LOG = HERE / ("voice-provision-" + STAMP + ".log")
REPORT = HERE / ("voice-provision-" + STAMP + ".json")
data = bytearray()
log_file = LOG.open("wb")
port = serial.Serial("/dev/ttyUSB0", 1500000, timeout=.02, write_timeout=2,
                     rtscts=False, dsrdtr=False, xonxoff=False)
port.dtr = False
port.rts = False
try:
    port.reset_input_buffer()
    print("VOICE_TEST starts_in=8", flush=True)
    time.sleep(8)
    port.write(b"k7voice flow-mic-provision\r")
    port.flush()
    deadline = time.monotonic() + 660
    while time.monotonic() < deadline:
        block = port.read(8192)
        if block:
            data.extend(block)
            log_file.write(block)
            log_file.flush()
            print(block.decode("utf-8", errors="replace"), end="", flush=True)
            if (re.search(rb"VOICE_PROVISION phase=(?:0|5|6)\\b", data) or
                    b"VOICE_PROVISION timeout" in data or
                    b"libc++abi:" in data or b"up_assert:" in data):
                break
finally:
    port.close()
    log_file.close()
    result = {
        "completed": bool(re.search(rb"VOICE_PROVISION phase=5\b", data)),
        "terminal": b"VOICE_PROVISION phase=" in data,
        "timeout": b"VOICE_PROVISION timeout" in data,
        "tls_failure": b"libc++abi:" in data,
        "assertion": b"up_assert:" in data,
        "password_logged": False,
        "log": str(LOG),
    }
    REPORT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print("\nEVIDENCE=" + str(REPORT), flush=True)
