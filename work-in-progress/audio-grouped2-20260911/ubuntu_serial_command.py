"""Run one bounded NSH command through the Ubuntu-owned K7 debug UART."""

import argparse
import re
import sys
import time
from pathlib import Path

import serial


def collect(port, seconds):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data.extend(port.read(4096))
    return bytes(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--label", default="command")
    args = parser.parse_args()
    if args.seconds <= 0 or args.seconds > 180:
        raise SystemExit("seconds must be in (0, 180]")

    output_dir = Path(__file__).resolve().parent
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = output_dir / (args.label + "-" + stamp + ".log")
    port = serial.Serial(
        args.port,
        args.baud,
        timeout=0.02,
        write_timeout=2,
        rtscts=False,
        dsrdtr=False,
        xonxoff=False,
    )
    port.dtr = False
    port.rts = False
    try:
        initial = collect(port, 1.0)
        port.write(b"\r")
        port.flush()
        prompt = collect(port, 3.0)
        if not re.search(rb"nsh>\s*$", initial + prompt):
            port.write(b"\x03\r")
            port.flush()
            prompt += collect(port, 3.0)
        port.write(args.command.encode("utf-8") + b"\r")
        port.flush()
        result = collect(port, args.seconds)
    finally:
        port.close()

    payload = initial + prompt + result
    log_path.write_bytes(payload)
    sys.stdout.write(payload.decode("utf-8", errors="replace"))
    sys.stdout.write("\nK7_LOG=" + str(log_path) + "\n")
    if b"nsh>" not in prompt:
        raise SystemExit("NSH prompt was not observed before command")


if __name__ == "__main__":
    main()
