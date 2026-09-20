#!/usr/bin/env python3
"""Resume the already RAM-booted BLE provisioning and Wi-Fi services.

This helper is intentionally bounded and never sends reset, fastboot, flash, or
credential commands.  It only waits for NSH and starts the two shared services.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

import serial


PORT = "/dev/ttyUSB0"
BAUD = 1_500_000
HERE = pathlib.Path(__file__).resolve().parent


def read_until(ser: serial.Serial, markers: tuple[bytes, ...], timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    output = bytearray()
    while time.monotonic() < deadline:
        chunk = ser.read(4096)
        if chunk:
            output.extend(chunk)
            if any(marker in output for marker in markers):
                return bytes(output)
        else:
            time.sleep(0.02)
    return bytes(output)


def command(ser: serial.Serial, text: str, marker: bytes, timeout: float) -> bytes:
    ser.reset_input_buffer()
    ser.write((text + "\r").encode("ascii"))
    ser.flush()
    data = read_until(ser, (marker, b"nsh>"), timeout)
    if marker not in data:
        raise RuntimeError(f"missing marker for {text!r}: {marker!r}")
    return data


def main() -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = HERE / f"ble-services-resume-{stamp}.log"
    result_path = HERE / f"ble-services-resume-{stamp}.json"
    transcript = bytearray()
    result = {
        "port": PORT,
        "baud": BAUD,
        "reset_sent": False,
        "flash_written": False,
        "wifi_service_started": False,
        "native_network": False,
    }
    try:
        with serial.Serial(PORT, BAUD, timeout=0.15, write_timeout=2) as ser:
            # A carriage return is enough to recover an already-running NSH.
            ser.write(b"\r")
            ser.flush()
            data = read_until(ser, (b"nsh>",), 20)
            transcript.extend(data)
            if b"nsh>" not in data:
                raise RuntimeError("NSH prompt was not observed; no interrupt was sent")

            data = command(ser, "k7radio wifi-service-start", b"WIFI shared start ret=0", 60)
            transcript.extend(data)
            result["wifi_service_started"] = True

            data = command(ser, "k7voice probe", b"VOICE native_network=1", 20)
            transcript.extend(data)
            result["native_network"] = True

        result["passed"] = True
        return_code = 0
    except Exception as exc:  # evidence must preserve the exact bounded failure
        result["passed"] = False
        result["error"] = str(exc)
        return_code = 1
    finally:
        log_path.write_bytes(bytes(transcript))
        result["log"] = log_path.name
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    return return_code


if __name__ == "__main__":
    sys.exit(main())
