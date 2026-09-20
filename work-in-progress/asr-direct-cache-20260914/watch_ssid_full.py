"""Recover through serial, wait for OTG, then RAM-boot the SSID prompt build."""

import fcntl
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
PROJECT = Path("/home/swl/openvela/work/velavision-project")
HELPER = PROJECT / "work-in-progress/tts-spoken-flow-20260913/load_prefix.py"
MANIFEST = HERE / "ssid-prefix-package.json"
PAYLOAD = HERE / "prompt-asr-direct-ssid-prefix.bin"
EXPECTED = "e67b65ce8d7bc20bad6646d67b2d00f6da37fc4ee128d2e6a0d787d2136ede88"


def log(message):
    print(time.strftime("%Y-%m-%dT%H:%M:%S%z"), message, flush=True)


def serial_ready():
    try:
        port = serial.Serial("/dev/ttyUSB0", 1_500_000, timeout=.02,
                             write_timeout=.2, rtscts=False, dsrdtr=False,
                             xonxoff=False)
        port.close()
        return True
    except (OSError, serial.SerialException):
        return False


def fastboot_ready():
    result = subprocess.run(["lsusb"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, timeout=10)
    return result.returncode == 0 and "18d1:4d00" in result.stdout.lower()


def verify():
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("sha256") != EXPECTED:
        raise RuntimeError("manifest hash mismatch")
    if manifest.get("flash_commands") is not False or manifest.get("emmc_written") is not False:
        raise RuntimeError("RAM-only gate failed")
    if PAYLOAD.stat().st_size != manifest.get("bytes"):
        raise RuntimeError("payload size mismatch")
    if hashlib.sha256(PAYLOAD.read_bytes()).hexdigest() != EXPECTED:
        raise RuntimeError("payload hash mismatch")


def main():
    with (HERE / "watch-ssid-full.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify()
        log("WATCH_SSID_FULL ready sha256=" + EXPECTED)
        deadline = time.monotonic() + 12 * 60 * 60
        entered = False
        attempt = 0
        while time.monotonic() < deadline and not entered:
            if fastboot_ready():
                entered = True
                break
            if not serial_ready():
                time.sleep(2)
                continue
            attempt += 1
            log("WATCH_SSID_FULL serial_ready attempt=%d" % attempt)
            entered = subprocess.run([sys.executable, str(HELPER), "enter"],
                                     cwd=str(HERE)).returncode == 0
            if not entered:
                entered = subprocess.run([sys.executable, str(HELPER), "uboot-enter"],
                                         cwd=str(HERE)).returncode == 0
            if not entered:
                log("WATCH_SSID_FULL enter_retry")
                time.sleep(2)
        if not entered:
            return 124
        log("WATCH_SSID_FULL fastboot_started")
        while time.monotonic() < deadline and not fastboot_ready():
            time.sleep(2)
        if not fastboot_ready():
            return 124
        time.sleep(1)
        if not fastboot_ready():
            raise RuntimeError("transient Fastboot device")
        log("WATCH_SSID_FULL otg_ready")
        result = subprocess.run([sys.executable, str(HERE / "load_ssid.py"), "transfer"],
                                cwd=str(HERE))
        log("WATCH_SSID_FULL transfer_exit=%d" % result.returncode)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
