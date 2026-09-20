"""Verify prompt playback, in-process ASR cache reuse, and explicit teardown."""

import hashlib
import json
import re
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
STAMP = time.strftime("%Y%m%d-%H%M%S")
LOG = HERE / ("board-acceptance-" + STAMP + ".log")
REPORT = HERE / ("board-acceptance-" + STAMP + ".json")
FIRMWARE_SHA256 = "26b95e41ca31460d8e2c9130d1daffbde9426a31b62027072c184fa7076f8992"


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
            if any(marker in output for marker in
                   (b"U-Boot SPL", b"PANIC", b"data abort", b"libc++abi")):
                raise RuntimeError("unexpected firmware restart or runtime fault")
            # UART reads can split the trailing ANSI clear-line sequence after
            # the prompt (for example, ``nsh> \x1b`` in one read and ``[K`` in
            # the next).  The prompt itself is the completion marker; limiting
            # the check to the tail avoids waiting for an escape sequence that
            # is cosmetic and may never arrive as one complete block.
            if b"nsh>" in output[-64:]:
                return bytes(output)
        raise RuntimeError("command timeout; no retry or reset sent")

    command("", 5)
    before = command("k7mem status", 10)
    prompt_before = command("k7voice prompt-smoke", 20)
    asr = command("k7voice asr-model", 240)
    after = command("k7mem status", 10)
    prompt_after = command("k7voice prompt-smoke", 20)

required_asr = [
    b"ASR_STORAGE direct encoder=0x80000000 decoder=0x90000000",
    b"ASR_CACHE hit=0",
    b"ASR_MODEL iteration=1 result=0",
    b"ASR_CACHE hit=1",
    b"ASR_MODEL iteration=2 result=0",
    b"ASR_CACHE reset=1",
]
missing = [item.decode() for item in required_asr if item not in asr]
if missing:
    raise RuntimeError("ASR acceptance missing markers: " + ", ".join(missing))
for output in (prompt_before, prompt_after):
    if b"VOICE_PROMPT_SMOKE result=0" not in output:
        raise RuntimeError("prompt playback failed")
if b"live=0" not in asr:
    raise RuntimeError("ASR model arena did not return to zero live bytes")

def infer_seconds(cache_hit):
    pattern = rb"ASR_CACHE hit=" + str(cache_hit).encode() + rb".*?ASR_INFER RESULT seconds=([0-9.]+)"
    found = re.search(pattern, asr, re.S)
    return float(found.group(1)) if found else None

report = {
    "status": "pass",
    "firmware_sha256": FIRMWARE_SHA256,
    "direct_retained_model_bytes": True,
    "cold_cache_hit": False,
    "warm_cache_hit": True,
    "cold_seconds": infer_seconds(0),
    "warm_seconds": infer_seconds(1),
    "explicit_cache_reset": True,
    "prompt_before_asr": True,
    "prompt_after_asr": True,
    "human_audibility_confirmed": False,
    "voice_provisioning_passed": False,
    "before_status_sha256": hashlib.sha256(before).hexdigest(),
    "after_status_sha256": hashlib.sha256(after).hexdigest(),
    "log_sha256": hashlib.sha256(LOG.read_bytes()).hexdigest(),
}
REPORT.write_text(json.dumps(report, indent=2) + "\n")
print("\nACCEPTANCE=" + str(REPORT))
