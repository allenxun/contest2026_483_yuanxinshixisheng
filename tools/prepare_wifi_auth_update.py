"""Advance known project snapshots only; no live SDK hash auto-approval."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];known={}
def allow(path,digest):known.setdefault(path,set()).add(digest)
for item in json.loads((ROOT/'evidence/source-files.json').read_text())['files']:allow(item['path'],item['sha256'])
for rev in ('phone-pairing','phone-rpa','credentials','eapol-rx'):
    for path,digest in json.loads((ROOT/f'evidence/build/{rev}-20260909/verification.json').read_text())['sources'].items():allow(path,digest)
for name in ('phone-pairing-update','phone-rpa-update','wifi-auth-update'):
    prior=ROOT/f'private/{name}/manifest.json'
    if prior.exists():
        for path,item in json.loads(prior.read_text()).items():
            allow(path,item['new'])
            for digest in item['previous']:allow(path,digest)
paths=[str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'app/k7radio').rglob('*') if p.is_file()]
staging='evidence/sync/wifi-auth-20260909.json'
(ROOT/staging).parent.mkdir(parents=True,exist_ok=True)
(ROOT/staging).write_text(json.dumps({p:sorted(v) for p,v in known.items() if p.startswith('app/k7radio/')},indent=2))
paths.append(staging)
paths+=['tools/sync_sdk.py','tools/build_wifi_auth.sh','tools/verify_wifi_auth_vm.py','tools/test_supplicant_vm.py','tests/wifi/test_supplicant.c','evidence/build/phone-rpa-20260909/verification.json']
out=ROOT/'private/wifi-auth-update';out.mkdir(exist_ok=True)
manifest={p:dict(new=hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),previous=sorted(known.get(p,set()))) for p in paths}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(out/'update.tar.gz','w:gz') as archive:
    for p in paths:archive.add(ROOT/p,arcname=p)
(out/'apply_update.py').write_text((ROOT/'tools/apply_phone_pairing_update_vm.py').read_text().replace('phone-pairing-update','wifi-auth-update'))
print('Packaged',len(paths),'explicit files')
