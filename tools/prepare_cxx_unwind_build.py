"""Apply reviewed two-file candidate and prepare a distinct native build."""
import hashlib
import json
import subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
paths=['board/kickpi_k7/scripts/dramboot.ld','board/kickpi_k7/src/kickpi_k7_appinit.c']
baseline=R/'evidence/sync/cxx-unwind-baseline.json'
assert not baseline.exists(), 'Already prepared'
before={p:[hashlib.sha256((R/p).read_bytes()).hexdigest()] for p in paths}
old=json.loads((R/'private/smp-load-original-hashes.json').read_text(encoding='utf-8-sig'))
old.update({p:v[0] for p,v in before.items()})
old['tools/sync_sdk.py']=hashlib.sha256((R/'tools/sync_sdk.py').read_bytes()).hexdigest()
(R/'private/cxx-unwind-original-hashes.json').write_text(json.dumps(old,indent=2)+'\n')
baseline.write_text(json.dumps(before,indent=2)+'\n')
patch=R/'work-in-progress/parallel-cxx-unwind-medium/candidate.patch'
subprocess.run(['git','-C',str(R),'apply','--check','--ignore-space-change',str(patch)],check=True)
subprocess.run(['git','-C',str(R),'apply','--ignore-space-change',str(patch)],check=True)
sync=R/'tools/sync_sdk.py'
s=sync.read_text()
marker='    # This unified board profile was created after the initial SDK inventory.'
assert marker in s
insert='''    # Exact canonical pre-edit hashes of the reviewed unwind board changes.
    unwind_stage=ROOT/'evidence/sync/cxx-unwind-baseline.json'
    if unwind_stage.exists():
        scope={'board/kickpi_k7/scripts/dramboot.ld','board/kickpi_k7/src/kickpi_k7_appinit.c'}
        for path,digests in json.loads(unwind_stage.read_text()).items():
            if path not in scope:raise RuntimeError('Unexpected unwind staging scope')
            approved.setdefault('nuttx/boards/arm64/rk3576/'+path[len('board/'):],set()).update(digests)
'''
sync.write_text(s.replace(marker,insert+marker),newline='\n')
p=R/'board/kickpi_k7/configs/velavision_cxx_unwind_local/defconfig'
p.parent.mkdir(parents=True)
p.write_text((R/'board/kickpi_k7/configs/velavision_cxx_tls_local/defconfig').read_text(),newline='\n')
for source,target in [('build_cxx_tls.sh','build_cxx_unwind.sh'),('build_cxx_tls_vm.py','build_cxx_unwind_vm.py')]:
    s=(R/'tools'/source).read_text().replace('cxx-tls','cxx-unwind').replace('cxx_tls','cxx_unwind')
    s=s.replace('private/smp-load-original-hashes.json','private/cxx-unwind-original-hashes.json')
    if target.endswith('.py'):
        s=s.replace('paths=list(dict.fromkeys(paths))', "paths += "+repr(paths+['evidence/sync/cxx-unwind-baseline.json'])+"\npaths=list(dict.fromkeys(paths))")
    (R/'tools'/target).write_text(s,newline='\n')
print('Prepared reviewed unwind source changes and independent build')
