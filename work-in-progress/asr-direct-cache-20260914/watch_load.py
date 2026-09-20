"""Wait for serial recovery, enter Fastboot, then load one RAM-only package."""

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
PROJECT = Path("/home/swl/openvela/work/velavision-project")
HELPER = PROJECT / "work-in-progress/tts-spoken-flow-20260913/load_prefix.py"
MANIFEST = HERE / "clean-tls-prefix-package.json"
PAYLOAD = HERE / "prompt-asr-direct-clean-tls-prefix.bin"
EXPECTED_SHA256 = "e97746d0e89f95843a396e6e3c343156e86d08e17068567b31222acd9e609926"
VID_PID = "18d1:4d00"


def log(message):
    print(time.strftime("%Y-%m-%dT%H:%M:%S%z"), message, flush=True)


def verify():
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("sha256") != EXPECTED_SHA256:
        raise RuntimeError("unexpected manifest hash")
    if manifest.get("flash_commands") is not False or manifest.get("emmc_written") is not False:
        raise RuntimeError("RAM-only manifest gate failed")
    if PAYLOAD.stat().st_size != manifest.get("bytes"):
        raise RuntimeError("payload size mismatch")
    if hashlib.sha256(PAYLOAD.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError("payload hash mismatch")


def serial_ready():
    try:
        port = serial.Serial("/dev/ttyUSB0", 1500000, timeout=.02,
                             write_timeout=.2, rtscts=False, dsrdtr=False,
                             xonxoff=False)
        port.close()
        return True
    except (OSError, serial.SerialException):
        return False


def fastboot_ready():
    result = subprocess.run(["lsusb"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, timeout=10)
    return result.returncode == 0 and VID_PID in result.stdout.lower()


def environment():
    value = os.environ.copy()
    value["K7VOICE_PACKAGE_DIR"] = str(HERE)
    value["K7VOICE_MANIFEST"] = str(MANIFEST)
    value["K7VOICE_PAYLOAD"] = str(PAYLOAD)
    return value


def main():
    lock = (HERE / "watch-direct-clean-tls.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("prompt2 watcher already active")
    lock.write(str(os.getpid()) + "\n")
    lock.flush()
    verify()
    log("WATCH_DIRECT_CLEAN_TLS ready ram_only=1 sha256=" + EXPECTED_SHA256)

    deadline = time.monotonic() + 12 * 60 * 60
    env = environment()
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
        log("WATCH_DIRECT_CLEAN_TLS serial_ready attempt=%d" % attempt)
        entered = subprocess.run(
            [sys.executable, str(HERE / "load.py"), "enter"],
            cwd=str(HERE), env=env,
        ).returncode == 0
        if not entered:
            log("WATCH_DIRECT_CLEAN_TLS nsh_enter_failed_trying_uboot")
            entered = subprocess.run(
                [sys.executable, str(HELPER), "uboot-enter"],
                cwd=str(HERE), env=env,
            ).returncode == 0
        if not entered:
            log("WATCH_DIRECT_CLEAN_TLS enter_retry")
            time.sleep(2)
    if not entered:
        log("WATCH_DIRECT_CLEAN_TLS enter_failed")
        return 1
    log("WATCH_DIRECT_CLEAN_TLS fastboot_started")

    while time.monotonic() < deadline and not fastboot_ready():
        time.sleep(2)
    if not fastboot_ready():
        return 124
    time.sleep(1)
    if not fastboot_ready():
        log("WATCH_DIRECT_CLEAN_TLS transient_fastboot")
        return 1
    log("WATCH_DIRECT_CLEAN_TLS otg_ready")
    result = subprocess.run([sys.executable, str(HERE / "load.py"), "transfer"],
                            cwd=str(HERE), env=env)
    log("WATCH_DIRECT_CLEAN_TLS transfer_exit=%d" % result.returncode)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

