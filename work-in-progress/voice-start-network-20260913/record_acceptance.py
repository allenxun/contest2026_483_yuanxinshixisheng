import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
E = PROJECT / 'evidence/voice-start-network-20260913'
A = PROJECT / 'artifacts/voice-start-network-20260913'
build = json.loads((E / 'result.json').read_text())
assert build['build_exit_code'] == 0
for rel, digest in build['inputs'].items():
    assert hashlib.sha256((PROJECT / rel).read_bytes()).hexdigest() == digest, rel
for name, data in build['artifacts'].items():
    b = (A / name).read_bytes()
    assert len(b) == data['bytes'] and hashlib.sha256(b).hexdigest() == data['sha256']
assert json.loads((E / 'unwind.json').read_text())['passed']
host = PROJECT / 'evidence/voicelink-core-integration-20260910/run-20260913T094927365382Z/result.json'
assert json.loads(host.read_text())['passed']
boot = (E / 'ram-final-20260913-175451.log').read_bytes()
for crc in (b'988d4301', b'b20f998f', b'2af64aa7', b'15121f1a'):
    assert crc in boot
prep = (E / 'voice-prepare-20260913-175720.log').read_bytes()
assert b'WIFI shared start ret=0' in prep and b'RADIO bt-host ret=0' in prep
last = (E / 'mic-wake-scan-20260913-175924.log').read_bytes()
assert b'VOICE_FLOW mic_state=0' in last and b'nsh>' in last
record = {
    'revision': 'voice-start-network-20260913',
    'firmware_sha256': build['artifacts']['nuttx.bin']['sha256'],
    'wake_rule': 'normalized text starts with 你好, or matches 开始联网',
    'host_flow_scenarios': 20, 'host_O0_O2_passed': True,
    'runtime_logging_tests': 'runtime-test.json',
    'arm64_build_passed': True, 'elf_unwind_passed': True,
    'ram_crc_passed': True, 'initial_boot_script_timeout': True,
    'nsh_verified_by_followup': True,
    'wireless_host_ready': True, 'wifi_service_ready': True,
    'wifi_connected': False, 'phone_ble_connected': None,
    'phone_ble_note': 'Host initialized; client connection not separately rechecked',
    'latest_microphone_asr_text': '哦', 'wake_to_scan_passed': False,
    'voice_provisioning_passed': False,
    'remaining': ['Capture cue timing / ASR accuracy', 'Actual voice-triggered scan',
                  'Network selection, spoken credentials, confirmation, real connection'],
    'scope': 'Rule change deployed; no claim that actual wake recognition passed',
    'flash_written': False, 'gimbal_started': False,
}
(E / 'acceptance.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in E.iterdir() if p.is_file() and p.name != 'sha256.json'}
(E / 'sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('PASS build and deployment evidence; live voice wake remains NOT PASSED')
