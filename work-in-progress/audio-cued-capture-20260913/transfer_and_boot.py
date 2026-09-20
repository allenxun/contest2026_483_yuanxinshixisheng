"""Transfer the reviewed voice-provision payload over Fastboot and RAM boot it.

This orchestrator only calls the download-only Fastboot client and the audited
serial CRC/copy/boot sequence.  It contains no flash, erase or eMMC command.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "prefix-package.json"
PAYLOAD = HERE / "audio-cued-capture-prefix.bin"
DOWNLOADER = HERE.parent / "voice-rule-provision-20260912/fastboot_ram_download.py"
LOADER = HERE / "load_prefix.py"
USB_DEPS = HERE.parent / "voice-rule-provision-20260912/vendor/pyusb"
USB_SERIAL = "f71a9d152132db55"


def run_checked(command, *, env=None, timeout=180):
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env,
                            timeout=timeout, check=False)
    output = result.stdout
    print(output.decode("utf-8", errors="replace"), end="", flush=True)
    if result.returncode != 0:
        raise RuntimeError("command failed with exit code %d" % result.returncode)
    return output


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("flash_commands") is not False:
        raise RuntimeError("manifest must explicitly prohibit flash commands")
    if PAYLOAD.stat().st_size != manifest["bytes"]:
        raise RuntimeError("payload size mismatch")
    digest = hashlib.sha256(PAYLOAD.read_bytes()).hexdigest()
    if digest != manifest["sha256"]:
        raise RuntimeError("payload SHA256 mismatch")
    if not DOWNLOADER.is_file() or not LOADER.is_file():
        raise RuntimeError("required reviewed helper missing")
    if not (USB_DEPS / "usb" / "__init__.py").is_file():
        raise RuntimeError("fixed PyUSB dependency missing; run restore_pyusb.py")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    usb_result = HERE / ("fixed-fixture-usb-" + stamp + ".json")
    acceptance = HERE / ("fixed-fixture-boot-" + stamp + ".json")
    if usb_result.exists() or acceptance.exists():
        raise RuntimeError("refusing to overwrite evidence")

    environment = os.environ.copy()
    prior = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(USB_DEPS) + ((":" + prior) if prior else "")
    started = time.monotonic()
    usb_output = run_checked([
        sys.executable, str(DOWNLOADER), str(PAYLOAD),
        "--sha256", digest,
        "--vid", "0x18d1",
        "--pid", "0x4d00",
        "--serial", USB_SERIAL,
        "--audited-running-buffer", "0x40c00800:0x07000000",
        "--result", str(usb_result),
    ], env=environment, timeout=180)
    boot_output = run_checked([sys.executable, str(LOADER), "final"],
                              timeout=240)
    if b"nsh>" not in boot_output:
        raise RuntimeError("RAM firmware did not expose NSH prompt")

    usb_record = json.loads(usb_result.read_text(encoding="utf-8"))
    record = {
        "payload_sha256": digest,
        "payload_bytes": manifest["bytes"],
        "payload_crc32": manifest["crc32"],
        "usb_serial": USB_SERIAL,
        "usb_ack": usb_record.get("usb_ack") is True,
        "usb_seconds": usb_record.get("seconds"),
        "ram_boot_reached_nsh": True,
        "boot_output_sha256": hashlib.sha256(boot_output).hexdigest(),
        "usb_output_sha256": hashlib.sha256(usb_output).hexdigest(),
        "elapsed_seconds": time.monotonic() - started,
        "flash_commands": False,
        "emmc_written": False,
    }
    acceptance.write_text(json.dumps(record, indent=2) + "\n",
                          encoding="utf-8")
    print("ACCEPTANCE=" + str(acceptance), flush=True)


if __name__ == "__main__":
    main()

