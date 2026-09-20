"""Wait for the exact Fastboot device, then run the reviewed RAM-only loader."""

import fcntl
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
TIMEOUT_SECONDS = 7200


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


def main():
    lock_path = HERE / "otg-wait.lock"
    lock = lock_path.open("w", encoding="ascii")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("another OTG waiter is already active")
    lock.write(str(os.getpid()) + "\n")
    lock.flush()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    report = HERE / ("otg-wait-" + stamp + ".json")
    deadline = time.monotonic() + TIMEOUT_SECONDS
    outcome = {
        "started_at": stamp,
        "timeout_seconds": TIMEOUT_SECONDS,
        "usb_serial": SERIAL,
        "device_seen": False,
        "transfer_started": False,
        "transfer_exit_code": None,
        "flash_commands": False,
        "emmc_written": False,
    }
    try:
        while time.monotonic() < deadline:
            if exact_device_present():
                outcome["device_seen"] = True
                print("OTG_DEVICE_READY", flush=True)
                break
            time.sleep(1)
        else:
            outcome["error"] = "OTG wait timeout"
            raise RuntimeError(outcome["error"])

        outcome["transfer_started"] = True
        process = subprocess.run(
            [sys.executable, str(HERE / "transfer_and_boot.py")],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=480, check=False,
        )
        sys.stdout.buffer.write(process.stdout)
        sys.stdout.buffer.flush()
        outcome["transfer_exit_code"] = process.returncode
        outcome["transfer_output_bytes"] = len(process.stdout)
        if process.returncode != 0:
            raise RuntimeError("transfer_and_boot failed")
        outcome["completed"] = True
    except Exception as error:
        outcome["completed"] = False
        outcome["error"] = str(error)
        raise
    finally:
        outcome["elapsed_seconds"] = TIMEOUT_SECONDS - max(
            0, deadline - time.monotonic())
        report.write_text(json.dumps(outcome, indent=2) + "\n",
                          encoding="utf-8")
        print("WAIT_REPORT=" + str(report), flush=True)


if __name__ == "__main__":
    main()
