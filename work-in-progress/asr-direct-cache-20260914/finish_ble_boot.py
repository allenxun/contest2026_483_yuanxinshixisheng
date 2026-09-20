"""Finish the RAM-only radio load for BLE provisioning, then boot.

This path intentionally does not claim that retained local ASR/TTS model
regions are valid.  It is used after the product flow has been changed to BLE
SSID/password provisioning followed by cloud speech.  The downloaded package,
radio blobs and firmware are still CRC-gated, and no flash command is issued.
"""

import json
import time

import radio_refresh as rr


def main():
    manifest = json.loads(rr.MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("flash_commands") is not False:
        raise RuntimeError("RAM-only manifest required")
    with rr.open_port() as port:
        port.write(b"\x03\r")
        port.flush()
        rr.read_to_prompt(port, 5)
        rr.check_crc(port, rr.DOWNLOAD_BASE, manifest["bytes"],
                     manifest["crc32"])
        for segment in manifest["segments"]:
            source = rr.DOWNLOAD_BASE + segment["offset"]
            rr.copy_chunks(port, source, segment["target"], segment["bytes"])
            rr.check_crc(port, segment["target"], segment["bytes"],
                         segment["crc32"])
        if b"edfe0dd0" not in rr.command(port, "md.l 48300000 1").lower():
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

    stamp = time.strftime("%Y%m%d-%H%M%S")
    report = {
        "status": "pass",
        "profile": "ble_wifi_then_cloud_speech",
        "payload_sha256": manifest["sha256"],
        "radio_segments_verified": 4,
        "firmware_verified": True,
        "local_speech_models_verified": False,
        "local_asr_available": False,
        "ram_boot_reached_nsh": True,
        "flash_commands": False,
        "emmc_written": False,
    }
    path = rr.HERE / ("ble-radio-boot-acceptance-" + stamp + ".json")
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("ACCEPTANCE=" + str(path), flush=True)


if __name__ == "__main__":
    main()
