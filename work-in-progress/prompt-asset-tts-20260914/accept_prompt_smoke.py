"""Run one bounded prompt playback and record machine-verifiable evidence."""

import hashlib
import json
import re
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
STAMP = time.strftime("%Y%m%d-%H%M%S")
LOG = HERE / ("prompt-smoke-" + STAMP + ".log")
REPORT = HERE / ("prompt-smoke-" + STAMP + ".json")


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
    output = command("k7voice prompt-smoke", 20)
    after = command("k7mem status", 10)

required = [
    b"VOICE_PROMPT_ASSET key=wake",
    b"VOICE_PROMPT_SMOKE result=0",
    b"SOUND playback_gain_db=24 dac_attenuation_db=0",
    b"SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0",
]
missing = [item.decode() for item in required if item not in output]
if missing:
    raise RuntimeError("prompt smoke missing markers: " + ", ".join(missing))
report = {
    "status": "pass",
    "firmware_sha256": "e9f48b37b769aa2ee6221ec344e37c242418ef2a35444a3252140afe9eef207f",
    "prompt_key": "wake",
    "prompt_speaker_id": 21,
    "target_peak_ratio": 0.90,
    "codec_dac_attenuation_db": 0,
    "machine_playback_passed": True,
    "human_audibility_confirmed": False,
    "before_status_sha256": hashlib.sha256(before).hexdigest(),
    "after_status_sha256": hashlib.sha256(after).hexdigest(),
    "log_sha256": hashlib.sha256(LOG.read_bytes()).hexdigest(),
    "voice_provisioning_passed": False,
}
REPORT.write_text(json.dumps(report, indent=2) + "\n")
print("\nACCEPTANCE=" + str(REPORT))
