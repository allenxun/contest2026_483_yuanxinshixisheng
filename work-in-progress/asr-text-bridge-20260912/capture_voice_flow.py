"""Cue, capture three seconds, and run microphone text through the real Controller."""

import json
import re
import time
from pathlib import Path

import serial


out = Path("/tmp") / ("voice-asr-text-flow-" + time.strftime("%Y%m%d-%H%M%S"))
out.mkdir()
port = serial.Serial(port=None, baudrate=1500000, timeout=0.02, write_timeout=2)
port.dtr = False
port.rts = False
port.port = "/dev/ttyUSB0"
port.open()


def transact(name, command, timeout, markers, require_prompt=True):
    port.reset_input_buffer()
    port.write((command + "\r").encode("ascii"))
    port.flush()
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data.extend(port.read(8192))
        marked = any(marker in data for marker in markers)
        prompted = bool(re.search(rb"nsh>\s*(?:\x1b\[K)?$", data))
        if marked and (prompted or not require_prompt):
            break
    (out / (name + ".log")).write_bytes(data)
    print(data.decode("utf-8", errors="replace"), flush=True)
    return data


result = {}
try:
    prompt = transact("prompt", "", 3, [b"nsh>"])
    result["prompt"] = b"nsh>" in prompt
    result["cue"] = True
    for cue_index in range(1, 4):
        cue = transact(
            "cue-%u" % cue_index,
            "k7sound tone",
            12,
            [b"SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0"],
        )
        cue_ok = b"SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0" in cue
        result["cue"] = result["cue"] and cue_ok
        if not cue_ok:
            raise RuntimeError("cue failed")
    capture = transact(
        "capture",
        "k7sound capture-pga24-grouped 48000",
        15,
        [b"SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0"],
    )
    result["capture"] = b"SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0" in capture
    if not result["capture"]:
        raise RuntimeError("capture failed")
    flow = transact(
        "flow",
        "k7voice flow-mic-wake &",
        210,
        [b"VOICE_FLOW mic_state=", b"VOICE_FLOW asr_error="],
        require_prompt=False,
    )
    result["wake_text"] = b"VOICE_FLOW wake_text=" in flow
    result["flow_terminal"] = b"VOICE_FLOW mic_state=" in flow
    result["asr_error"] = b"VOICE_FLOW asr_error=" in flow
finally:
    port.close()
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("EVIDENCE=" + str(out), flush=True)
