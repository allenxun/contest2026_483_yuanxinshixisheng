import json
from pathlib import Path


path = Path(__file__).resolve().parents[2] / "project-manifest.json"
data = json.loads(path.read_text(encoding="utf-8"))
data["updated_at"] = "2026-09-14T13:10:00+08:00"
data["current_device"] = {
    "revision": "unknown-after-sharedcache2-asr-panic-20260914",
    "state": "The sharedcache2 RAM image played cold and warm male TTS, then data-aborted while creating the ASR Session from a retained TTS Session. It auto-rebooted; the current image and retained model CRCs have not been revalidated because the VMware CH340 endpoint now returns I/O error.",
    "ram_booted": False,
    "flash_written": False,
    "wifi_online": False,
    "ble_online": None,
    "radio_host_online": False,
    "wifi_shared_service_online": False,
    "decoder_staging_crc_verified": None,
    "encoder_tail_crc_verified": None,
    "previous_manual_wifi_user_confirmed": True,
    "previous_manual_wifi_revision": "voice-ui-connect-20260913",
    "previous_prompt_playback_passed": True,
    "previous_tts_cold_seconds": 9.043,
    "previous_tts_warm_seconds": 3.022,
    "combined_cached_tts_asr_passed": False,
    "combined_failure": "NuttX system-heap allocation failed for 960 bytes in OrtApis::CreateSessionOptions while the separate 512 MiB model arena still had 529492464 bytes free",
    "voice_wifi_provisioning_passed": False,
    "evidence": "docs/离线TTS语音配网接入_20260913.md",
}
data["pending_firmware"] = {
    "revision": "prompt-asr2-20260914",
    "status": "Twenty pre-generated male provisioning prompts, heap-free mono S16 playback, and cached online Paraformer ASR are linked and packaged. Host O0/O2 PIO regressions and ELF/package bounds passed. Loading is waiting for the VMware QinHeng USB Serial endpoint to be disconnected and reconnected because /dev/ttyUSB0 opens with I/O error.",
    "sha256": "e9f48b37b769aa2ee6221ec344e37c242418ef2a35444a3252140afe9eef207f",
    "payload_sha256": "3018c2f0769faff89a7f32f50e0152f07ba372224eadb1fe6d69ebaacfbf3172",
    "payload_bytes": 117122920,
    "payload_headroom_bytes": 317592,
    "prompt_assets": 20,
    "runtime_tts_enabled": False,
    "hardware_tested": False,
    "ram_boot_verified": False,
    "flash_commands": False,
    "emmc_written": False,
    "evidence": "work-in-progress/prompt-asset-tts-20260914/prompt-asr2-prefix-package.json",
}
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(path)
