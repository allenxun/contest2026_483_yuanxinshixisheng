"""Package explicit known source snapshots for native IPv4 development."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];known={}
def allow(p,h):known.setdefault(p,set()).add(h)
for item in json.loads((ROOT/'evidence/source-files.json').read_text(encoding='utf-8'))['files']:allow(item['path'],item['sha256'])
for rev in ('phone-pairing','phone-rpa','credentials','eapol-rx','wifi-auth'):
    for p,h in json.loads((ROOT/f'evidence/build/{rev}-20260909/verification.json').read_text(encoding='utf-8'))['sources'].items():allow(p,h)
for name in ('phone-pairing-update','phone-rpa-update','wifi-auth-update','wifi-ip-update'):
    prior=ROOT/f'private/{name}/manifest.json'
    if prior.exists():
        for p,item in json.loads(prior.read_text(encoding='utf-8')).items():
            allow(p,item['new'])
            for h in item['previous']:allow(p,h)
paths=[p.relative_to(ROOT).as_posix() for p in (ROOT/'app/k7radio').rglob('*') if p.is_file()]
staging='evidence/sync/wifi-ip-20260909.json'
(ROOT/staging).write_text(json.dumps({p:sorted(v) for p,v in known.items() if p.startswith('app/k7radio/') or p.startswith('board/kickpi_k7/configs/velavision_wifi_ip_local/')},indent=2),encoding='utf-8')
paths += [staging,'tools/sync_sdk.py','tools/build_wifi_ip.sh','tools/verify_wifi_ip_vm.py','tools/test_supplicant_vm.py','tests/wifi/test_supplicant.c','tests/wifi/test_wifi_data.c','evidence/build/wifi-auth-20260909/verification.json','board/kickpi_k7/configs/velavision_wifi_ip_local/defconfig']
paths.append('tools/verify_wifi_ip_rx_vm.py')
paths += ['tools/verify_wifi_amsdu_vm.py','tests/wifi/test_amsdu.c','tools/verify_wifi_amsdu_diag_vm.py','tools/verify_wifi_amsdu_index_vm.py','tools/build_wifi_ip_incremental.sh']
out=ROOT/'private/wifi-ip-update';out.mkdir(exist_ok=True)
manifest={p:dict(new=hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),previous=sorted(known.get(p,set()))) for p in paths}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
with tarfile.open(out/'update.tar.gz','w:gz') as archive:
    for p in paths:archive.add(ROOT/p,arcname=p)
(out/'apply_update.py').write_text((ROOT/'tools/apply_phone_pairing_update_vm.py').read_text().replace('phone-pairing-update','wifi-ip-update'),encoding='utf-8')
print('Packaged',len(paths),'explicit files')
