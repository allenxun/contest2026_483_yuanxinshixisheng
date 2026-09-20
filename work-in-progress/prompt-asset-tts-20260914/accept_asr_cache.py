"""Run the fixed ASR fixture twice and verify recognizer cache reuse."""

import hashlib
import json
import re
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
STAMP = time.strftime("%Y%m%d-%H%M%S")
LOG = HERE / ("asr-cache-" + STAMP + ".log")
REPORT = HERE / ("asr-cache-" + STAMP + ".json")


with LOG.open("xb") as log, serial.Serial(
        "/dev/ttyUSB0", 1500000, timeout=.03, write_timeout=2,
        exclusive=True) as port:
    port.dtr = False
    port.rts = False

    def command(text, timeout):
        port.write(text.encode() + b"\r")
        port.flush()
        output = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            block = port.read(8192)
            if block:
                log.write(block)
                log.flush()
                output.extend(block)
                print(block.decode(errors="replace"), end="", flush=True)
            if b"U-Boot SPL" in output or b"PANIC" in output or b"data abort" in output:
                raise RuntimeError("unexpected firmware restart or fault")
            if re.search(rb"nsh>\s*(?:\x1b\[K)?\s*$", output):
                return bytes(output)
        raise RuntimeError("command timeout; no retry or reset sent")

    command("", 5)
    before = command("k7mem status", 10)
    cold = command("k7voice asr-model", 180)
    warm = command("k7voice asr-model", 180)
    after = command("k7mem status", 10)

if b"ASR_MODEL result=0" not in cold or b"ASR_CACHE hit=0" not in cold:
    raise RuntimeError("cold ASR probe did not pass or unexpectedly used cache")
if b"ASR_MODEL result=0" not in warm or b"ASR_CACHE hit=1" not in warm:
    raise RuntimeError("warm ASR probe did not pass with cache reuse")

def seconds(output):
    found = re.search(rb"ASR_INFER RESULT seconds=([0-9.]+)", output)
    return float(found.group(1)) if found else None

report = {
    "status": "pass",
    "firmware_sha256": "e9f48b37b769aa2ee6221ec344e37c242418ef2a35444a3252140afe9eef207f",
    "cold_cache_hit": False,
    "warm_cache_hit": True,
    "cold_seconds": seconds(cold),
    "warm_seconds": seconds(warm),
    "before_status_sha256": hashlib.sha256(before).hexdigest(),
    "after_status_sha256": hashlib.sha256(after).hexdigest(),
    "log_sha256": hashlib.sha256(LOG.read_bytes()).hexdigest(),
}
REPORT.write_text(json.dumps(report, indent=2) + "\n")
print("\nACCEPTANCE=" + str(REPORT))
