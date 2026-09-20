"""Run two ambient-only captures to prove ASR error cleanup and retry safety."""

import json
import re
import time
from pathlib import Path

import serial


OUT = Path("/tmp") / ("voice-asr-empty-retry-" + time.strftime("%Y%m%d-%H%M%S"))
OUT.mkdir()
PORT = serial.Serial("/dev/ttyUSB0", 1500000, timeout=.02, write_timeout=2,
                     rtscts=False, dsrdtr=False, xonxoff=False)
PORT.dtr = False
PORT.rts = False


def transact(name, command, timeout, markers, require_prompt):
    PORT.reset_input_buffer()
    PORT.write((command + "\r").encode("ascii"))
    PORT.flush()
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data.extend(PORT.read(8192))
        marked = any(marker in data for marker in markers)
        prompt = bool(re.search(rb"nsh>\s*(?:\x1b\[K)?$", data))
        if marked and (prompt or not require_prompt):
            time.sleep(.5)
            data.extend(PORT.read(8192))
            break
    (OUT / (name + ".log")).write_bytes(data)
    print(data.decode("utf-8", errors="replace"), flush=True)
    return bytes(data)


rows = []
try:
    for attempt in (1, 2):
        capture = transact(
            "capture-%u" % attempt,
            "k7sound capture-pga24-grouped 48000",
            20,
            [b"SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0"],
            True,
        )
        flow = transact(
            "flow-%u" % attempt,
            "k7voice flow-mic-wake &",
            210,
            [b"VOICE_FLOW asr_error=", b"VOICE_FLOW mic_state="],
            False,
        )
        terminal = b"VOICE_FLOW asr_error=" in flow or b"VOICE_FLOW mic_state=" in flow
        clean = b"libc++abi:" not in flow and b"ASR_INFER busy" not in flow
        row = {
            "attempt": attempt,
            # High-volume ISR diagnostics can interleave with the label on UART;
            # the counters and terminal cleanup marker are the stable contract.
            "grouped_capture_ok": b"768000 mismatches=0" in capture,
            "capture_cleanup_ok": b"SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0" in capture,
            "terminal": terminal,
            "clean_exit": clean,
            "empty_result": b"VOICE_FLOW asr_error=-61" in flow,
        }
        rows.append(row)
        if not all((row["capture_cleanup_ok"], terminal, clean)):
            raise RuntimeError("ASR retry attempt failed")
finally:
    PORT.close()
    (OUT / "result.json").write_text(json.dumps({"attempts": rows}, indent=2) + "\n",
                                      encoding="utf-8")
print("EVIDENCE=" + str(OUT), flush=True)
