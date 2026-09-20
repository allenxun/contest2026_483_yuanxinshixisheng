"""Record verified host-stage integration without claiming board execution."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_report', type=Path)
    args = parser.parse_args()
    report_path = args.test_report.resolve()
    assert report_path.is_relative_to(ROOT / 'evidence/voicelink-core-integration-20260910')
    test = json.loads(report_path.read_text(encoding='utf-8'))
    assert test['passed'] and test['source_unchanged'] and not test['hardware_tested']
    assert len(test['steps']) == 4 and all(s.get('exit_code') == 0 for s in test['steps'])
    for name, digest in test['source_after'].items():
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT / 'app/voicelink') and sha(path) == digest
    deliveries = []
    for folder, manifest_name in (
            ('parallel-cxx-unwind-medium/audio-i2c3-clock-v1', 'delivery.json'),
            ('parallel-model-reader-medium/audio-codec-capture-review-v1', 'delivery.json'),
            ('parallel-neon-probe-medium/voice-wifi-scan-contract-v1', 'outputs.json')):
        base = ROOT / 'work-in-progress' / folder
        manifest = base / manifest_name
        value = json.loads(manifest.read_text(encoding='utf-8'))
        entries = value.get('files', value)
        items = entries if isinstance(entries, list) else [dict(path=n, sha256=h) for n, h in entries.items()]
        for item in items:
            path = (base / item['path']).resolve()
            assert path.is_relative_to(base) and sha(path) == item['sha256'], str(path)
        deliveries.append(dict(directory=folder, manifest_sha256=sha(manifest), verified_files=len(items)))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    stage = dict(updated_at=now, priority='Local voice provisioning first; cloud model after true network',
                 test_report=str(report_path.relative_to(ROOT)), test_report_sha256=sha(report_path),
                 source_hashes=test['source_after'], deliveries=deliveries,
                 formal_core=True, asynchronous_scan_interface=True,
                 radio_scan_backend_integrated=False, firmware_integrated=False,
                 hardware_tested=False, local_llm_required=False,
                 local_asr_tts_still_required=True,
                 doc='docs/本地语音配网优先实施_20260910.md')
    dump(ROOT / 'evidence/voicelink-core-integration-20260910/stage.json', stage)
    manifest_path = ROOT / 'project-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['updated_at'] = now
    manifest['voice_provisioning_stage'] = stage
    pending = manifest.get('pending_firmware', {})
    if pending.get('revision') == 'fat-readonly-20260910':
        build = json.loads((ROOT / 'evidence/build/fat-readonly-20260910/verification.json').read_text(encoding='utf-8'))
        assert build['build_exit_code'] == 0 and not build['hardware_tested']
        for name, item in build['artifacts'].items():
            assert sha(ROOT / 'artifacts/fat-readonly-20260910' / name) == item['sha256']
        pending.update(compiled=True, hardware_tested=False, board_unchanged=True,
                       state='Compiled; not RAM loaded; remains useful for local speech-model storage',
                       binary_sha256=build['artifacts']['nuttx.bin']['sha256'])
    dump(manifest_path, manifest)
    print(json.dumps({'formal_test_passed': True, 'deliveries': deliveries,
                      'hardware_tested': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
