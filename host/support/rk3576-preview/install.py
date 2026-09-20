from pathlib import Path
import hashlib,json
r=Path('/home/swl/openvela');w=r/'work/rk3576-preview';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan=json.loads((w/'install-plan.json').read_text())
for i in plan:
    p=r/i['target'];assert (not p.exists() if not i['old_sha256'] else sha(p)==i['old_sha256']),i['target']
    assert sha(w/i['local'])==i['new_sha256'],i['local']
for i in plan:(r/i['target']).write_bytes((w/i['local']).read_bytes())
print('Installed',len(plan),'hash-gated v23 preview changes')
