"""Capture an unfiltered TTS -> ASR -> TTS serial trace."""

import hashlib
import json
import re
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
STAMP = time.strftime("%Y%m%d-%H%M%S")
LOG = HERE / ("sharedcache-probe-" + STAMP + ".log")
REPORT = HERE / ("sharedcache-probe-" + STAMP + ".json")


def run(port, log, text, timeout):
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
        if b"U-Boot SPL" in output or b"PANIC" in output:
            raise RuntimeError("unexpected firmware restart or fault")
        if re.search(rb"nsh>\s*(?:\x1b\[K)?\s*$", output):
            return bytes(output)
    raise RuntimeError("timeout: " + text)


with LOG.open("xb") as log, serial.Serial(
        "/dev/ttyUSB0", 1500000, timeout=.03, write_timeout=2,
        exclusive=True) as port:
    port.dtr = False
    port.rts = False
    run(port, log, "", 5)
    outputs = {
        "help": run(port, log, "help", 15),
        "tts_cold": run(port, log, "k7voice tts-smoke", 240),
        "asr_cold": run(port, log, "k7voice asr-model", 240),
        "asr_warm": run(port, log, "k7voice asr-model", 240),
        "tts_warm": run(port, log, "k7voice tts-smoke", 240),
    }

checks = {
    "k7mem_listed": b"k7mem" in outputs["help"],
    "k7voice_listed": b"k7voice" in outputs["help"],
    "tts_cold_ok": b"VOICE_TTS result=0" in outputs["tts_cold"],
    "asr_cold_ok": b"ASR_MODEL result=0" in outputs["asr_cold"],
    "asr_warm_ok": b"ASR_MODEL result=0" in outputs["asr_warm"],
    "tts_warm_ok": b"VOICE_TTS result=0" in outputs["tts_warm"],
    "shared_attach_seen": b"SR_ATTACH" in b"".join(outputs.values()),
    "no_allocator_failure": b"SR_ATTACH status=failed" not in
                            b"".join(outputs.values()),
}
report = {
    "status": "pass" if all(checks.values()) else "fail",
    "checks": checks,
    "log_sha256": hashlib.sha256(LOG.read_bytes()).hexdigest(),
    "ram_only": True,
    "emmc_written": False,
}
REPORT.write_text(json.dumps(report, indent=2) + "\n")
print("\nREPORT=" + str(REPORT))
print(json.dumps(report, indent=2))
if report["status"] != "pass":
    raise SystemExit(1)
