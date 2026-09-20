"""Explicit mirror update; prior build/manifests are the only accepted hashes."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];known={}
def allow(path,digest):known.setdefault(path,set()).add(digest)
for item in json.loads((ROOT/'evidence/source-files.json').read_text())['files']:allow(item['path'],item['sha256'])
for path,item in json.loads((ROOT/'private/phone-pairing-update/manifest.json').read_text()).items():
    allow(path,item['new'])
    for digest in item['previous']:allow(path,digest)
for path,digest in json.loads((ROOT/'evidence/build/phone-pairing-20260909/verification.json').read_text())['sources'].items():allow(path,digest)
paths=['port/tracked/nuttx/wireless/bluetooth/'+n for n in ('bt_smp.c','bt_conn.h','bt_hcicore.c')]
paths+=['tools/sync_sdk.py','tools/build_phone_rpa.sh','tools/verify_phone_rpa_vm.py','tests/bluetooth/test_pairing_addresses.c','evidence/build/phone-pairing-20260909/verification.json']
out=ROOT/'private/phone-rpa-update';out.mkdir(exist_ok=True)
if (out/'manifest.json').exists():
    for path,item in json.loads((out/'manifest.json').read_text()).items():
        allow(path,item['new'])
        for digest in item['previous']:allow(path,digest)
manifest={p:dict(new=hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),previous=sorted(known.get(p,set()))) for p in paths}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(out/'update.tar.gz','w:gz') as archive:
    for p in paths:archive.add(ROOT/p,arcname=p)
script=(ROOT/'tools/apply_phone_pairing_update_vm.py').read_text().replace('phone-pairing-update','phone-rpa-update')
(out/'apply_update.py').write_text(script)
print('Packaged',len(paths),'explicit files')
