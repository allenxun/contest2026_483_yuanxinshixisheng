"""Resume radio startup after an SDIO command completed beyond an old prompt deadline."""

import json
import re
import time
from pathlib import Path

import serial


def run_stage(port, name, command, timeout, required):
    port.reset_input_buffer()
    port.write((command + "\r").encode("ascii"))
    port.flush()
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data.extend(port.read(8192))
        if re.search(rb"nsh>\s*(?:\x1b\[K)?$", data):
            break
    Path(name + ".log").write_bytes(data)
    passed = all(marker in data for marker in required)
    result = {
        "stage": name,
        "command": command,
        "required": [marker.decode("ascii") for marker in required],
        "prompt": b"nsh>" in data,
        "passed": passed,
    }
    print(data.decode("utf-8", errors="replace"), flush=True)
    print(json.dumps(result), flush=True)
    if not passed:
        raise RuntimeError("failed stage " + name)
    return result


out = Path("/tmp") / ("voice-asr-text-radio-" + time.strftime("%Y%m%d-%H%M%S"))
out.mkdir()
results = []
port = serial.Serial(port=None, baudrate=1500000, timeout=0.02, write_timeout=2)
port.dtr = False
port.rts = False
port.port = "/dev/ttyUSB0"
port.open()
try:
    time.sleep(2)
    port.reset_input_buffer()
    stages = [
        ("bluetooth", "k7radio bt-host", 40, [b"connect=true advertise=0"]),
        ("service", "k7radio wifi-service-start", 20, [b"WIFI shared start ret=0"]),
        ("probe", "k7voice probe", 15, [b"VOICE native_network=1"]),
        ("scan", "k7voice scan", 50, [b"VOICE scan_done"]),
    ]
    for stage in stages:
        results.append(run_stage(port, *stage))
finally:
    port.close()
    (out / "result.json").write_text(
        json.dumps({"results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
print("EVIDENCE=" + str(out), flush=True)
