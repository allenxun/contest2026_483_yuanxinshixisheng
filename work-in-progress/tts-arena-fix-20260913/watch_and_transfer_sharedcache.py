"""Wait for the reviewed Fastboot gadget, then perform one RAM-only transfer."""

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "spoken-tts-gated-sharedcache-prefix.bin"
MANIFEST = HERE / "sharedcache-prefix-package.json"
EXPECTED_SHA256 = "7c514734a13fd8a2a515a25c137ed82ec9e547910ea63390e21641509d9e3407"
VID_PID = "18d1:4d00"
WAIT_SECONDS = 12 * 60 * 60
POLL_SECONDS = 2
MAX_ATTEMPTS = 3


def log(message):
    print(time.strftime("%Y-%m-%dT%H:%M:%S%z"), message, flush=True)


def fastboot_present():
    result = subprocess.run(["lsusb"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False,
                            text=True, timeout=10)
    return result.returncode == 0 and VID_PID in result.stdout.lower()


def verify_inputs():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("flash_commands") is not False:
        raise RuntimeError("manifest does not prohibit flash commands")
    if manifest.get("sha256") != EXPECTED_SHA256:
        raise RuntimeError("manifest SHA256 is not the reviewed package")
    if PAYLOAD.stat().st_size != manifest.get("bytes"):
        raise RuntimeError("payload size mismatch")
    digest = hashlib.sha256(PAYLOAD.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError("payload SHA256 mismatch")


def main():
    lock_path = HERE / "transfer-watch-sharedcache.lock"
    lock = lock_path.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("another transfer watcher is already active")
    lock.write(str(os.getpid()) + "\n")
    lock.flush()

    verify_inputs()
    log("WATCH ready vid_pid=%s package_sha256=%s" % (VID_PID, EXPECTED_SHA256))
    deadline = time.monotonic() + WAIT_SECONDS
    next_status = 0.0
    attempts = 0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_status:
            log("WATCH waiting attempts=%d" % attempts)
            next_status = now + 60
        if not fastboot_present():
            time.sleep(POLL_SECONDS)
            continue
        time.sleep(1)
        if not fastboot_present():
            log("WATCH transient_device")
            continue
        attempts += 1
        log("WATCH device_ready attempt=%d" % attempts)
        result = subprocess.run(
            [sys.executable, str(HERE / "load_sharedcache.py"), "transfer"],
            cwd=str(HERE), check=False)
        log("WATCH transfer_exit=%d attempt=%d" % (result.returncode, attempts))
        if result.returncode == 0:
            log("WATCH completed")
            return 0
        if attempts >= MAX_ATTEMPTS:
            log("WATCH failed max_attempts=%d" % MAX_ATTEMPTS)
            return result.returncode or 1
        time.sleep(5)
    log("WATCH timeout seconds=%d" % WAIT_SECONDS)
    return 124


if __name__ == "__main__":
    raise SystemExit(main())










