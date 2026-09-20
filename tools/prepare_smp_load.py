"""Stage the bounded compute diagnostic as a new immutable build revision."""
import hashlib
import json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
profile = R / 'board/kickpi_k7/configs/velavision_smp_load_local/defconfig'
assert not profile.exists()
profile.parent.mkdir(parents=True)
profile.write_text((R / 'board/kickpi_k7/configs/velavision_smp_service_local/defconfig').read_text() + '\nCONFIG_EXAMPLES_K7LOAD=y\n', newline='\n')
for old, new in [('build_smp_service.sh', 'build_smp_load.sh'), ('build_smp_service_vm.py', 'build_smp_load_vm.py')]:
    s = (R / 'tools' / old).read_text()
    s = s.replace('smp-service-20260910', 'smp-load-20260910').replace('smp_service', 'smp_load')
    s = s.replace('smp-service-stage-20260910', 'smp-load-stage-20260910').replace('smp-service-original-hashes', 'smp-load-original-hashes')
    if new.endswith('_vm.py'):
        s = s.replace('paths=list(dict.fromkeys(paths))', "paths += [str(p.relative_to(R)).replace('\\\\','/') for p in sorted((R/'app/k7load').iterdir()) if p.is_file()]\npaths=list(dict.fromkeys(paths))")
        s = s.replace("'CONFIG_SMP=y','CONFIG_SMP_NCPUS=8'", "'CONFIG_EXAMPLES_K7LOAD=y','CONFIG_SMP=y','CONFIG_SMP_NCPUS=8'")
    (R / 'tools' / new).write_text(s, newline='\n')
old = {}
for subtree in ['app', 'port', 'board']:
    for p in (R / subtree).rglob('*'):
        if p.is_file(): old[p.relative_to(R).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
for p in [R / 'tools/sync_sdk.py', R / 'evidence/sync/smp-diag-baseline.json']:
    old[p.relative_to(R).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
(R / 'private/smp-load-original-hashes.json').write_text(json.dumps(old))
print('Prepared smp-load; no board operations')
