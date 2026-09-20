"""Build and RAM-load the missing Seekwave radio staging data.

The package contains the four immutable radio blobs and the already reviewed
voice-provision firmware.  It never issues Fastboot flash/erase commands and
does not touch eMMC.  ASR/TTS retained regions are CRC-gated again before boot.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zlib
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
PROJECT = Path("/home/swl/openvela/work/velavision-project")
VOICE_HELPERS = PROJECT / "work-in-progress/tts-spoken-flow-20260913"
DOWNLOADER = PROJECT / "work-in-progress/voice-rule-provision-20260912/fastboot_ram_download.py"
USB_DEPS = PROJECT / "work-in-progress/voice-rule-provision-20260912/vendor/pyusb"
RADIO_DIR = Path("/home/swl/k7-armbian/kickpi-armbian/packages/bsp/kickpi/usr/lib/firmware")
FIRMWARE = Path("/home/swl/openvela/cmake_out/velavision_prompt_asr_direct_ssid_20260914/nuttx.bin")
PAYLOAD = HERE / "radio-refresh.bin"
MANIFEST = HERE / "radio-refresh.json"
DOWNLOAD_BASE = 0x40C00800
FIRMWARE_OFFSET = 0x01000000
USB_SERIAL = "f71a9d152132db55"

INPUTS = (
    ("SWT6621S_DRAM_SDIO.bin", 0x000000, 0x50000000, 193224,
     "7ddaae63b3281a4127565b2a7306fc74f8e5c7e88343a43c56a17d05a27d2b4b"),
    ("SWT6621S_IRAM_SDIO.bin", 0x040000, 0x50100000, 356616,
     "07d316bbf4dd18cc95671366c5001560f272026454fef1f6e134eb197189a169"),
    ("sv6160lite.nvbin", 0x0A0000, 0x50180000, 37,
     "1bb53545c5d67500c6141353b7ba8e2c8cb4b8b61d2f0835eec218f7a37efd44"),
    ("SWT6621S_SEEKWAVE_R00001.bin", 0x0A1000, 0x50190000, 2372,
     "b20c04399d69f067d28bb07c24d3c2b1dca795f44e617a83cf6d254ef8715010"),
)
FIRMWARE_BYTES = 16529040
FIRMWARE_SHA256 = "26b95e41ca31460d8e2c9130d1daffbde9426a31b62027072c184fa7076f8992"
FIRMWARE_CRC32 = 0x8024E62C


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build():
    firmware = FIRMWARE.read_bytes()
    if len(firmware) != FIRMWARE_BYTES or digest(firmware) != FIRMWARE_SHA256:
        raise RuntimeError("reviewed firmware mismatch")
    total = FIRMWARE_OFFSET + len(firmware)
    payload = bytearray(total)
    segments = []
    occupied = []
    for name, offset, target, size, expected in INPUTS:
        data = (RADIO_DIR / name).read_bytes()
        if len(data) != size or digest(data) != expected:
            raise RuntimeError("radio input mismatch: " + name)
        end = offset + len(data)
        if any(not (end <= left or right <= offset) for left, right in occupied):
            raise RuntimeError("overlapping package layout")
        occupied.append((offset, end))
        payload[offset:end] = data
        segments.append({"name": name, "offset": offset, "target": target,
                         "bytes": len(data), "sha256": expected,
                         "crc32": "%08x" % (zlib.crc32(data) & 0xFFFFFFFF)})
    payload[FIRMWARE_OFFSET:] = firmware
    segments.append({"name": "nuttx.bin", "offset": FIRMWARE_OFFSET,
                     "target": 0x40400000, "bytes": len(firmware),
                     "sha256": FIRMWARE_SHA256,
                     "crc32": "%08x" % FIRMWARE_CRC32})
    PAYLOAD.write_bytes(payload)
    record = {"bytes": len(payload), "sha256": digest(payload),
              "crc32": "%08x" % (zlib.crc32(payload) & 0xFFFFFFFF),
              "download_base": DOWNLOAD_BASE, "segments": segments,
              "retained_encoder_crc32": "b20f998f",
              "retained_decoder_crc32": "2af64aa7",
              "retained_tts_crc32": "9efc1996",
              "flash_commands": False, "emmc_written": False}
    MANIFEST.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2), flush=True)


def open_port():
    port = serial.Serial("/dev/ttyUSB0", 1500000, timeout=.02, write_timeout=2,
                         rtscts=False, dsrdtr=False, xonxoff=False)
    port.dtr = port.rts = False
    return port


def read_to_prompt(port, seconds):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        block = port.read(8192)
        if block:
            data.extend(block)
            print(block.decode(errors="replace"), end="", flush=True)
        if re.search(rb"(?:^|\n)=>\s*$", data):
            return bytes(data)
    raise RuntimeError("U-Boot prompt timeout")


def command(port, text, seconds=30):
    port.write(text.encode("ascii") + b"\r")
    port.flush()
    output = read_to_prompt(port, seconds)
    if b"Unknown command" in output or b"Usage:" in output:
        raise RuntimeError("U-Boot rejected " + text)
    return output


def check_crc(port, address, size, expected):
    output = command(port, "crc32 %x %x" % (address, size))
    if not re.search(rb"==>\s*" + expected.encode("ascii") + rb"\b", output):
        raise RuntimeError("CRC mismatch at 0x%x" % address)


def copy_chunks(port, source, target, size):
    if not (source + size <= target or target + size <= source):
        raise RuntimeError("overlapping copy refused")
    for offset in range(0, size, 0x400000):
        count = min(0x400000, size - offset)
        command(port, "cp.b %x %x %x" % (source + offset, target + offset, count))


def enter():
    environment = os.environ.copy()
    environment["K7VOICE_PACKAGE_DIR"] = str(HERE)
    environment["K7VOICE_MANIFEST"] = str(HERE / "ssid-prefix-package.json")
    environment["K7VOICE_PAYLOAD"] = str(HERE / "prompt-asr-direct-ssid-prefix.bin")
    result = subprocess.run([sys.executable, str(VOICE_HELPERS / "load_prefix.py"), "enter"],
                            env=environment, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def transfer():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("flash_commands") is not False:
        raise RuntimeError("RAM-only manifest required")
    if PAYLOAD.stat().st_size != manifest["bytes"] or digest(PAYLOAD.read_bytes()) != manifest["sha256"]:
        raise RuntimeError("radio refresh payload mismatch")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(USB_DEPS) + (":" + environment["PYTHONPATH"]
                                                  if environment.get("PYTHONPATH") else "")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    usb_result = HERE / ("radio-refresh-usb-" + stamp + ".json")
    result = subprocess.run([
        sys.executable, str(DOWNLOADER), str(PAYLOAD), "--sha256", manifest["sha256"],
        "--vid", "0x18d1", "--pid", "0x4d00", "--serial", USB_SERIAL,
        "--audited-running-buffer", "0x40c00800:0x07000000", "--result", str(usb_result)
    ], env=environment, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    with open_port() as port:
        port.write(b"\x03")
        port.flush()
        read_to_prompt(port, 5)
        check_crc(port, DOWNLOAD_BASE, manifest["bytes"], manifest["crc32"])
        check_crc(port, 0x80000000, 0x9E7DA30, manifest["retained_encoder_crc32"])
        check_crc(port, 0x90000000, 0x44B0310, manifest["retained_decoder_crc32"])
        check_crc(port, 0x96000000, 0x1FB2400, manifest["retained_tts_crc32"])
        for segment in manifest["segments"]:
            source = DOWNLOAD_BASE + segment["offset"]
            copy_chunks(port, source, segment["target"], segment["bytes"])
            check_crc(port, segment["target"], segment["bytes"], segment["crc32"])
        if b"edfe0dd0" not in command(port, "md.l 48300000 1").lower():
            raise RuntimeError("DTB magic mismatch")
        port.write(b"booti 40400000 - 48300000\r")
        port.flush()
        output = bytearray()
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            block = port.read(8192)
            if block:
                output.extend(block)
                print(block.decode(errors="replace"), end="", flush=True)
            if b"nsh>" in output:
                break
        else:
            port.write(b"\r")
            port.flush()
            if b"nsh>" not in port.read(8192):
                raise RuntimeError("RAM firmware did not reach NSH")
    report = {"status": "pass", "payload_sha256": manifest["sha256"],
              "payload_bytes": manifest["bytes"], "usb_result": str(usb_result),
              "radio_segments_verified": 4, "firmware_verified": True,
              "retained_models_verified": True, "ram_boot_reached_nsh": True,
              "flash_commands": False, "emmc_written": False}
    path = HERE / ("radio-refresh-acceptance-" + stamp + ".json")
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("ACCEPTANCE=" + str(path), flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"build", "enter", "transfer"}:
        raise SystemExit("usage: radio_refresh.py build|enter|transfer")
    {"build": build, "enter": enter, "transfer": transfer}[sys.argv[1]]()
