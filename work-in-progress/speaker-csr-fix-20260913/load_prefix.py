"""Enter Fastboot or verify/copy/boot the RAM-only voice rule provisioning payload."""

import hashlib
import json
import re
import sys
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
MODE = sys.argv[1]
LOG = (HERE / ("ram-" + MODE + "-" + time.strftime("%Y%m%d-%H%M%S") + ".log")).open("xb")


def open_port():
    port = serial.Serial("/dev/ttyUSB0", 1500000, timeout=.02, write_timeout=2,
                         rtscts=False, dsrdtr=False, xonxoff=False)
    port.dtr = False
    port.rts = False
    return port


def read(port, seconds, pattern=None):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data.extend(port.read(4096))
        if pattern and re.search(pattern, data):
            break
    LOG.write(data)
    LOG.flush()
    print(data.decode(errors="replace"), end="", flush=True)
    return bytes(data)


def command(port, text, seconds=15):
    port.write(text.encode() + b"\r")
    port.flush()
    output = read(port, seconds, rb"(?:^|\n)=>\s*$")
    if not re.search(rb"(?:^|\n)=>\s*$", output):
        raise RuntimeError("U-Boot prompt missing after " + text)
    if b"Unknown command" in output or b"Usage:" in output:
        raise RuntimeError("U-Boot rejected " + text)
    return output


def check_crc(port, address, size, expected):
    output = command(port, "crc32 %x %x" % (address, size), 30)
    if not re.search(rb"==>\s+" + expected.encode() + rb"\b", output):
        raise RuntimeError("CRC mismatch at %x" % address)


def copy_nonoverlap(port, source, target, size):
    if not (source + size <= target or target + size <= source):
        raise RuntimeError("overlapping copy refused")
    for offset in range(0, size, 0x400000):
        count = min(0x400000, size - offset)
        command(port, "cp.b %x %x %x" % (source + offset, target + offset, count))


def enter_fastboot(port):
    port.write(b"fastboot usb 1\r")
    port.flush()
    output = read(port, 3)
    if b"Enter fastboot...OK" not in output:
        raise RuntimeError("Fastboot gadget did not start")


def reset_to_uboot(port):
    """Work around failed gadget re-entry; callers must recheck RAM after reset."""
    port.write(b"reset\r")
    port.flush()
    output = bytearray()
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        block = port.read(4096)
        output.extend(block)
        LOG.write(block)
        LOG.flush()
        if b"U-Boot 2017" in output:
            port.write(b"\x03")
            port.flush()
            time.sleep(.05)
        if re.search(rb"(?:^|\n)=>\s*$", output):
            break
    print(output.decode(errors="replace"), end="", flush=True)
    if not re.search(rb"(?:^|\n)=>\s*$", output):
        raise RuntimeError("Reset did not reach intercepted U-Boot; stopped")


try:
    if MODE == "stage-decoder":
        with open_port() as port:
            port.write(b"\x03\r")
            port.flush()
            output = read(port, 5, rb"(?:^|\n)=>\s*$")
            if not re.search(rb"(?:^|\n)=>\s*$", output):
                raise RuntimeError("U-Boot prompt missing")
            check_crc(port, 0x40C00800, 0x44B0310, "2af64aa7")
            copy_nonoverlap(port, 0x40C00800, 0x90000000, 0x44B0310)
            check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
            enter_fastboot(port)
    elif MODE in ("stage-tail", "stage-tail-reset"):
        with open_port() as port:
            port.write(b"\x03\r")
            port.flush()
            output = read(port, 5, rb"(?:^|\n)=>\s*$")
            if not re.search(rb"(?:^|\n)=>\s*$", output):
                raise RuntimeError("U-Boot prompt missing")
            check_crc(port, 0x40C00800, 0x4E7DA30, "1696436b")
            check_crc(port, 0x41C00800, 0x3E7DA30, "b5f7ae2d")
            check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
            copy_nonoverlap(port, 0x41C00800, 0x86000000, 0x3E7DA30)
            check_crc(port, 0x86000000, 0x3E7DA30, "b5f7ae2d")
            check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
            if MODE == "stage-tail-reset":
                reset_to_uboot(port)
                check_crc(port, 0x86000000, 0x3E7DA30, "b5f7ae2d")
                check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
            enter_fastboot(port)
    elif MODE == "reset-enter":
        with open_port() as port:
            port.write(b"\x03\r")
            read(port, 5, rb"(?:^|\n)=>\s*$")
            reset_to_uboot(port)
            check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
            check_crc(port, 0x86000000, 0x3E7DA30, "b5f7ae2d")
            enter_fastboot(port)
    elif MODE == "uboot-enter":
        with open_port() as port:
            port.write(b"\x03\r")
            port.flush()
            output = read(port, 5, rb"(?:^|\n)=>\s*$")
            if not re.search(rb"(?:^|\n)=>\s*$", output):
                raise RuntimeError("U-Boot prompt missing")
            check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
            check_crc(port, 0x86000000, 0x3E7DA30, "b5f7ae2d")
            enter_fastboot(port)
    elif MODE == "enter":
        with open_port() as port:
            port.write(b"\r")
            if b"nsh>" not in read(port, 3):
                raise RuntimeError("NSH prompt missing; reboot not sent")
            port.write(b"reboot\r")
            output = bytearray()
            deadline = time.monotonic() + 22
            while time.monotonic() < deadline:
                block = port.read(4096)
                output.extend(block)
                LOG.write(block)
                LOG.flush()
                if b"U-Boot 2017" in output:
                    port.write(b"\x03")
                    port.flush()
                    time.sleep(.05)
                if re.search(rb"(?:^|\n)=>\s*$", output):
                    break
            print(output.decode(errors="replace"), end="", flush=True)
            if not re.search(rb"(?:^|\n)=>\s*$", output):
                raise RuntimeError("autoboot was not interrupted")
            check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
            check_crc(port, 0x86000000, 0x3E7DA30, "b5f7ae2d")
            enter_fastboot(port)
    elif MODE == "final":
        manifest = json.loads((HERE / "prefix-package.json").read_text(encoding="utf-8"))
        payload = HERE / "speaker-csr-prefix.bin"
        if hashlib.sha256(payload.read_bytes()).hexdigest() != manifest["sha256"]:
            raise RuntimeError("payload hash mismatch")
        with open_port() as port:
            port.write(b"\x03")
            port.flush()
            read(port, 5, rb"(?:^|\n)=>\s*$")
            check_crc(port, 0x40C00800, manifest["bytes"], manifest["crc32"])
            check_crc(port, 0x90000000, 0x44B0310, "2af64aa7")
            check_crc(port, 0x86000000, 0x3E7DA30, "b5f7ae2d")
            copy_nonoverlap(port, 0x40C00800, 0x80000000, 0x6000000)
            check_crc(port, 0x80000000, 0x9E7DA30, "b20f998f")
            copy_nonoverlap(port, 0x46C00800, 0x40400000, manifest["firmware_bytes"])
            check_crc(port, 0x40400000, manifest["firmware_bytes"],
                      manifest["firmware_crc32"])
            if b"edfe0dd0" not in command(port, "md.l 48300000 1").lower():
                raise RuntimeError("DTB magic mismatch")
            port.write(b"booti 40400000 - 48300000\r")
            port.flush()
            if b"nsh>" not in read(port, 30):
                raise RuntimeError("RAM firmware did not reach NSH")
    else:
        raise RuntimeError(
            "expected enter, stage-decoder, stage-tail, stage-tail-reset, uboot-enter or final"
        )
finally:
    LOG.close()
    print("\nK7_LOG=" + str(LOG.name))
