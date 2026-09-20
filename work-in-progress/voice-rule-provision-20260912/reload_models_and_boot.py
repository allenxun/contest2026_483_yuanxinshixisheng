"""Resume a full RAM-only ASR model reload after decoder staging.

The operator may need to reconnect the exact Fastboot gadget to the Ubuntu VM
between phases.  Every transfer is download-only; serial-side CRC checks and
non-overlapping copies run before the final RAM boot.
"""

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import usb.core
import usb.util


HERE = Path(__file__).resolve().parent
SERIAL = "f71a9d152132db55"
TAIL = Path(
    "/home/swl/openvela/work/native-asr-model-session/encoder1/"
    "encoder-part2-firmware.bin"
)
TAIL_BYTES = 82303536
TAIL_SHA256 = "b09cb375894244cda6c52c67b54dc64befdc771d21dce98ba09abcb80c5514f8"
TIMEOUT_SECONDS = 7200


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def exact_device_present():
    matches = []
    for device in usb.core.find(find_all=True, idVendor=0x18D1,
                                idProduct=0x4D00):
        try:
            if usb.util.get_string(device, device.iSerialNumber) == SERIAL:
                matches.append(device)
        finally:
            usb.util.dispose_resources(device)
    return len(matches) == 1


def wait_for_device(stage, outcome):
    print("WAIT_OTG=" + stage, flush=True)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if exact_device_present():
            time.sleep(0.5)
            outcome[stage + "_device_seen"] = True
            print("OTG_DEVICE_READY=" + stage, flush=True)
            return
        time.sleep(1)
    raise RuntimeError("OTG wait timeout during " + stage)


def run_checked(command, timeout):
    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    sys.stdout.buffer.write(process.stdout)
    sys.stdout.buffer.flush()
    if process.returncode != 0:
        raise RuntimeError("command failed: " + " ".join(command))


def main():
    lock = (HERE / "otg-reload.lock").open("w", encoding="ascii")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("another model reload is already active")
    lock.write(str(os.getpid()) + "\n")
    lock.flush()

    if TAIL.stat().st_size != TAIL_BYTES:
        raise RuntimeError("encoder tail bundle size mismatch")
    if sha256(TAIL) != TAIL_SHA256:
        raise RuntimeError("encoder tail bundle SHA256 mismatch")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    report = HERE / ("model-reload-" + stamp + ".json")
    tail_usb = HERE / ("encoder-tail-reload-usb-" + stamp + ".json")
    outcome = {
        "started_at": stamp,
        "decoder_staged_before_start": True,
        "tail_bytes": TAIL_BYTES,
        "tail_sha256": TAIL_SHA256,
        "usb_serial": SERIAL,
        "flash_commands": False,
        "emmc_written": False,
    }
    started = time.monotonic()
    try:
        wait_for_device("encoder_tail", outcome)
        run_checked([
            sys.executable,
            str(HERE / "fastboot_ram_download.py"),
            str(TAIL),
            "--sha256", TAIL_SHA256,
            "--vid", "0x18d1",
            "--pid", "0x4d00",
            "--serial", SERIAL,
            "--audited-running-buffer", "0x40c00800:0x07000000",
            "--result", str(tail_usb),
        ], timeout=180)
        outcome["tail_usb_ack"] = True
        run_checked([sys.executable, str(HERE / "load_ram.py"),
                     "stage-tail"], timeout=240)
        outcome["decoder_and_tail_crc_verified"] = True

        wait_for_device("final_package", outcome)
        run_checked([sys.executable, str(HERE / "transfer_and_boot.py")],
                    timeout=600)
        outcome["ram_boot_reached_nsh"] = True
        outcome["completed"] = True
    except Exception as error:
        outcome["completed"] = False
        outcome["error"] = str(error)
        raise
    finally:
        outcome["elapsed_seconds"] = time.monotonic() - started
        report.write_text(json.dumps(outcome, indent=2) + "\n",
                          encoding="utf-8")
        print("RELOAD_REPORT=" + str(report), flush=True)


if __name__ == "__main__":
    main()
