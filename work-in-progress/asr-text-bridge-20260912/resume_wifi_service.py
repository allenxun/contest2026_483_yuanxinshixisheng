"""Continue after the Bluetooth host printed PROV service ready beyond its deadline."""

import json
import re
import time
from pathlib import Path

import serial


out = Path("/tmp") / ("voice-asr-text-service-" + time.strftime("%Y%m%d-%H%M%S"))
out.mkdir()
port = serial.Serial(port=None, baudrate=1500000, timeout=0.02, write_timeout=2)
port.dtr = False
port.rts = False
port.port = "/dev/ttyUSB0"
port.open()
rows = []
try:
    time.sleep(2)
    port.reset_input_buffer()
    stages = [
        ("service", "k7radio wifi-service-start", 25, b"WIFI shared start ret=0"),
        ("probe", "k7voice probe", 15, b"VOICE native_network=1"),
        ("scan", "k7voice scan", 55, b"VOICE scan_done"),
    ]
    for name, command, timeout, marker in stages:
        port.reset_input_buffer()
        port.write((command + "\r").encode("ascii"))
        port.flush()
        data = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data.extend(port.read(8192))
            if marker in data and re.search(rb"nsh>\s*(?:\x1b\[K)?$", data):
                break
        (out / (name + ".log")).write_bytes(data)
        passed = marker in data
        rows.append({"stage": name, "command": command, "passed": passed})
        print(data.decode("utf-8", errors="replace"), flush=True)
        print(json.dumps(rows[-1]), flush=True)
        if not passed:
            raise RuntimeError("failed stage " + name)
finally:
    port.close()
    (out / "result.json").write_text(
        json.dumps({"results": rows}, indent=2), encoding="utf-8"
    )
print("EVIDENCE=" + str(out), flush=True)
