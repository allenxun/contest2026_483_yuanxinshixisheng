"""Update the manifest for the reviewed wake-partial build and current U-Boot state."""

from __future__ import print_function

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "project-manifest.json"
ACCEPTANCE_PATH = "evidence/voice-rule-wakepartial-20260912/acceptance.json"
ACCEPTANCE = json.loads((ROOT / ACCEPTANCE_PATH).read_text(encoding="utf-8"))
HOST_REPORT = (
    ROOT
    / "evidence"
    / "voicelink-core-integration-20260910"
    / "run-20260912T122301237955Z"
    / "result.json"
)

assert ACCEPTANCE["stage"] == "wake-partial-built-not-loaded"
assert ACCEPTANCE["passed"] is True
assert ACCEPTANCE["new_firmware_board_tested"] is False
assert ACCEPTANCE["boundaries"]["emmc_written"] is False

data = json.loads(MANIFEST.read_text(encoding="utf-8"))
assert data["current_device"]["revision"] == "voice-flow-confirmation-20260912"
assert data["pending_firmware"]["revision"] == "audio-pause-20260911"

data["updated_at"] = "2026-09-12T20:55:00+08:00"
data["current_device"] = {
    "revision": "u-boot-after-voice-wakepartial-package-20260912",
    "state": "U-Boot prompt",
    "ram_booted": False,
    "flash_written": False,
    "wifi_online": False,
    "ble_online": False,
    "radio_host_online": False,
    "wifi_shared_service_online": False,
    "decoder_staging_crc_verified": True,
    "encoder_tail_crc_verified": True,
    "previous_firmware": "voice-rule-provision-tlsrepeat-20260912",
    "previous_microphone_to_controller": True,
    "previous_microphone_asr_text": "你好 open",
    "previous_tls_repeat_passed": True,
    "previous_model_storage_released": True,
    "previous_controller_real_scan_passed": True,
    "audio_prompt_tone": True,
    "dynamic_tts": False,
    "evidence": ACCEPTANCE_PATH,
}

new_build = ACCEPTANCE["new_build"]
data["pending_firmware"] = {
    "revision": "voice-rule-provision-wakepartial-20260912",
    "status": "built, ELF-audited and packaged; OTG VMware proxy Code 43; not loaded",
    "sha256": new_build["firmware_sha256"],
    "payload_sha256": new_build["payload_sha256"],
    "payload_crc32": new_build["payload_crc32"],
    "payload_bytes": new_build["payload_bytes"],
    "flash_commands": False,
    "hardware_tested": False,
    "evidence": ACCEPTANCE_PATH,
}

stage = data["voice_provisioning_stage"]
stage.update(
    {
        "updated_at": "2026-09-12T20:55:00+08:00",
        "priority": "Local voice provisioning first; cloud model after true network",
        "test_report": (
            "evidence/voicelink-core-integration-20260910/"
            "run-20260912T122301237955Z/result.json"
        ),
        "test_report_sha256": hashlib.sha256(HOST_REPORT.read_bytes()).hexdigest(),
        "source_hashes": new_build["source_hashes"],
        "radio_scan_backend_integrated": True,
        "firmware_integrated": True,
        "microphone_to_controller": True,
        "audio_prompt_tone": True,
        "dynamic_tts": False,
        "complete": False,
        "hardware_tested": False,
        "hardware_scope": (
            "prior firmware microphone ASR reached Controller; new exact wake "
            "accommodation is built but not loaded"
        ),
        "blocker": "VMware USB proxy Code 43 prevents OTG RAM transfer",
        "acceptance": ACCEPTANCE_PATH,
        "next": (
            "restore OTG, load the reviewed RAM package, and complete wake, "
            "scan, selection, password, confirmation, WPA2/DHCP and IPv4"
        ),
    }
)

MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(MANIFEST)
