"""Catch a cold K7 boot and restore all ASR segments using OTG RAM downloads."""

import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
PROJECT = Path("/home/swl/openvela/work/velavision-project")
HELPER_DIR = PROJECT / "work-in-progress/tts-spoken-flow-20260913"
LOADER = HELPER_DIR / "load_prefix.py"
DOWNLOADER = PROJECT / "work-in-progress/voice-rule-provision-20260912/fastboot_ram_download.py"
USB_DEPS = PROJECT / "work-in-progress/voice-rule-provision-20260912/vendor/pyusb"
SERIAL = "f71a9d152132db55"
MAX_BUFFER = "0x40c00800:0x07000000"
DECODER = Path("/home/swl/openvela/work/native-asr-model-session/decoder.ort")
DECODER_SHA = "0f58ca4bd77728d8e512b852eff58e9aeedd90cfa2016ae40379b4700a78da14"
TAIL = Path("/home/swl/openvela/work/native-asr-model-session/encoder1/encoder-part2-firmware.bin")
TAIL_SHA = "b09cb375894244cda6c52c67b54dc64befdc771d21dce98ba09abcb80c5514f8"
LOG = HERE / "cold-reset-loader-20260914.log"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_fastboot(deadline):
    while time.monotonic() < deadline:
        found = subprocess.run(["lsusb"], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=10)
        if found.returncode == 0 and "18d1:4d00" in found.stdout.lower():
            time.sleep(1)
            return
        time.sleep(2)
    raise RuntimeError("Fastboot OTG timeout")


def download(path, expected, label):
    if digest(path) != expected:
        raise RuntimeError(label + " hash mismatch")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    result_path = HERE / ("cold-" + label + "-usb-" + stamp + ".json")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(USB_DEPS) + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    command = [
        sys.executable, str(DOWNLOADER), str(path), "--sha256", expected,
        "--vid", "0x18d1", "--pid", "0x4d00", "--serial", SERIAL,
        "--audited-running-buffer", MAX_BUFFER, "--result", str(result_path),
    ]
    if subprocess.run(command, env=env).returncode:
        raise RuntimeError(label + " USB download failed")


def enter_fastboot_after_reset():
    output = bytearray()
    with serial.Serial(port=None, baudrate=1_500_000, timeout=.02,
                       write_timeout=2) as port:
        port.dtr = False
        port.rts = False
        port.port = "/dev/ttyUSB0"
        port.open()
        port.reset_input_buffer()
        print("COLD_RESET armed", flush=True)
        deadline = time.monotonic() + 12 * 60 * 60
        last_interrupt = 0.0
        with LOG.open("ab") as log:
            while time.monotonic() < deadline:
                block = port.read(8192)
                if block:
                    output.extend(block)
                    if len(output) > 131072:
                        del output[:-65536]
                    log.write(block)
                    log.flush()
                    sys.stdout.buffer.write(block)
                    sys.stdout.flush()
                now = time.monotonic()
                if (b"U-Boot 2017" in output or b"Hit key to stop autoboot" in output) and now - last_interrupt >= .05:
                    port.write(b"\x03")
                    port.flush()
                    last_interrupt = now
                if re.search(rb"(?:^|\n)=>\s*$", output):
                    break
            else:
                raise RuntimeError("cold RESET was not observed")
        port.write(b"fastboot usb 1\r")
        port.flush()
        response = bytearray()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            response.extend(port.read(4096))
            if b"Enter fastboot...OK" in response:
                break
        if b"Enter fastboot...OK" not in response:
            raise RuntimeError("cold Fastboot start failed")
        print(response.decode(errors="replace"), end="", flush=True)


def run_stage(mode):
    if subprocess.run([sys.executable, str(LOADER), mode], cwd=str(HERE)).returncode:
        raise RuntimeError(mode + " failed")


def main():
    if DECODER.stat().st_size != 0x44B0310 or TAIL.stat().st_size != 0x4E7DA30:
        raise RuntimeError("model segment size mismatch")
    enter_fastboot_after_reset()
    deadline = time.monotonic() + 12 * 60 * 60
    wait_fastboot(deadline)
    download(DECODER, DECODER_SHA, "decoder")
    run_stage("stage-decoder")
    wait_fastboot(deadline)
    download(TAIL, TAIL_SHA, "encoder-tail")
    # Do not reset after placing the encoder tail at 0x86000000.  This board's
    # warm-reset DDR training can modify that range; the firmware boot path does
    # not require another reset and validates both model CRCs before use.
    run_stage("stage-tail")
    wait_fastboot(deadline)
    return subprocess.run([sys.executable, str(HERE / "load_ssid.py"), "transfer"],
                          cwd=str(HERE)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
