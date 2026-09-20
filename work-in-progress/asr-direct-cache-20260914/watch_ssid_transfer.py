"""Wait for the already-running Fastboot gadget, then load the SSID package."""

import fcntl
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "ssid-prefix-package.json"
PAYLOAD = HERE / "prompt-asr-direct-ssid-prefix.bin"
EXPECTED = "e67b65ce8d7bc20bad6646d67b2d00f6da37fc4ee128d2e6a0d787d2136ede88"


def log(message):
    print(time.strftime("%Y-%m-%dT%H:%M:%S%z"), message, flush=True)


def fastboot_ready():
    result = subprocess.run(["lsusb"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, timeout=10)
    return result.returncode == 0 and "18d1:4d00" in result.stdout.lower()


def main():
    with (HERE / "watch-ssid-transfer.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = json.loads(MANIFEST.read_text())
        if manifest.get("sha256") != EXPECTED:
            raise RuntimeError("manifest hash mismatch")
        if manifest.get("flash_commands") is not False or manifest.get("emmc_written") is not False:
            raise RuntimeError("RAM-only gate failed")
        if PAYLOAD.stat().st_size != manifest.get("bytes"):
            raise RuntimeError("payload size mismatch")
        if hashlib.sha256(PAYLOAD.read_bytes()).hexdigest() != EXPECTED:
            raise RuntimeError("payload hash mismatch")
        log("WATCH_SSID ready sha256=" + EXPECTED)
        deadline = time.monotonic() + 12 * 60 * 60
        while time.monotonic() < deadline and not fastboot_ready():
            time.sleep(2)
        if not fastboot_ready():
            return 124
        time.sleep(1)
        if not fastboot_ready():
            raise RuntimeError("transient Fastboot device")
        log("WATCH_SSID otg_ready")
        result = subprocess.run([sys.executable, str(HERE / "load_ssid.py"), "transfer"],
                                cwd=str(HERE))
        log("WATCH_SSID transfer_exit=%d" % result.returncode)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
