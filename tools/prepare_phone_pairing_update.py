"""Package only explicit project changes with previously recorded mirror hashes."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
known={}
def allow(path,digest):known.setdefault(path,set()).add(digest)
for item in json.loads((ROOT/'evidence/source-files.json').read_text())['files']:
    allow(item['path'],item['sha256'])
for revision in ('eapol-rx-20260909','credentials-20260909'):
    for path,digest in json.loads((ROOT/f'evidence/build/{revision}/verification.json').read_text())['sources'].items():allow(path,digest)
with tarfile.open(ROOT/'private/wpa-transport-update.tar.gz') as previous:
    for member in previous.getmembers():
        if member.isfile():allow(member.name,hashlib.sha256(previous.extractfile(member).read()).hexdigest())
paths=['app/k7radio/skw_bt.c','board/kickpi_k7/configs/velavision_integrated_local/defconfig','tools/sync_sdk.py',
       'tools/verify_phone_pairing_vm.py','evidence/build/credentials-20260909/verification.json',
       'port/tracked/nuttx/wireless/bluetooth/bt_keys.c','port/tracked/nuttx/wireless/bluetooth/Kconfig',
       'tests/bluetooth/test_pairing_pool.c','tools/test_pairing_pool_vm.py','tools/build_phone_pairing.sh']
out=ROOT/'private/phone-pairing-update';out.mkdir(exist_ok=True)
if (out/'manifest.json').exists():
    previous_manifest=json.loads((out/'manifest.json').read_text())
    for path,item in previous_manifest.items():
        allow(path,item['new'])
        for digest in item['previous']:allow(path,digest)
manifest={p:dict(new=hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),previous=sorted(known.get(p,set()))) for p in paths}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(out/'update.tar.gz','w:gz') as archive:
    for p in paths:archive.add(ROOT/p,arcname=p)
print('Packaged',len(paths),'explicit files with recorded prior hashes')
