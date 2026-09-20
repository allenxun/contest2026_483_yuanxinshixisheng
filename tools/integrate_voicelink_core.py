"""Migrate only the reviewed platform-independent VoiceLink core, by hash."""
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'work-in-progress/parallel-voicelink'
DEST = ROOT / 'app/voicelink'
FILES = ['include/voicelink/types.hpp', 'include/voicelink/ports.hpp',
         'include/voicelink/controller.hpp', 'include/voicelink/parsers.hpp',
         'src/core.cpp', 'src/parsers.cpp']


def main():
    delivery_path = SOURCE / 'evidence/delivery.json'
    delivery = json.loads(delivery_path.read_text(encoding='utf-8'))
    staged = {}
    for name in FILES:
        data = (SOURCE / name).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != delivery['files'][name]:
            raise SystemExit('Candidate drift: ' + name)
        target = DEST / name
        if target.exists() and target.read_bytes() != data:
            raise SystemExit('Refusing to overwrite formal changes: ' + name)
        staged[name] = (data, digest)
    for name, (data, _) in staged.items():
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
    evidence = ROOT / 'evidence/voicelink-core-integration-20260910'
    evidence.mkdir(parents=True, exist_ok=True)
    record = {
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source': str(SOURCE), 'destination': str(DEST),
        'delivery_sha256': hashlib.sha256(delivery_path.read_bytes()).hexdigest(),
        'files': {n: h for n, (_, h) in staged.items()},
        'scope': 'Core and rule parsers only; no old WAPI hooks or fake audio backend',
        'firmware_integrated': False, 'hardware_tested': False,
    }
    path = evidence / 'migration.json'
    if not path.exists():
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'verified_and_migrated_files': len(staged), 'hardware_tested': False}))


if __name__ == '__main__':
    main()
