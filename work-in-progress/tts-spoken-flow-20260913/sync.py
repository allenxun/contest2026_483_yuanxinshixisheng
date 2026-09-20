from pathlib import Path
import json,hashlib,subprocess,difflib
here=Path(__file__).resolve().parent
root=here.parents[1]
sdk=Path('/home/swl/openvela')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with (here/'sdk-before.log').open('xb') as log:
    subprocess.run(['python3',str(root/'tools/sync_sdk.py'),'--sdk',str(sdk),'--check'],stdout=log,stderr=subprocess.STDOUT,check=True)
pairs=[]; report=[]
known=json.loads((root/'work-in-progress/voice-ui-connect-20260913/inputs.json').read_text())
for name,digest in json.loads((here/'inputs.json').read_text()).items():
    src=here/'input'/name
    assert sha(src)==digest
    dest=(sdk/('apps/examples/'+name[4:]) if name.startswith('app/') else
          sdk/('nuttx/boards/arm64/rk3576/'+name[6:]) if name.startswith('board/') else
          sdk/name[len('port/new/'):])
    prior=root/name
    assert prior.exists()==dest.exists() or (prior.exists() and not dest.exists() and sha(prior)==digest),name
    if prior.exists():
        if dest.exists(): assert sha(prior)==sha(dest),name
        if name in known: assert sha(prior)==known[name],name
        before=here/'before'/name
        before.parent.mkdir(parents=True,exist_ok=True)
        before.write_bytes(prior.read_bytes())
        report.append(''.join(difflib.unified_diff(prior.read_text().splitlines(True),src.read_text().splitlines(True),fromfile=name,tofile=name)))
    pairs.extend([(src,prior),(src,dest)])
(here/'reviewed-source.patch').write_text('\n'.join(report))
# All validation completes before any project/SDK write.
for src,dest in pairs:
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(src.read_bytes())
(here/'sync-result.json').write_text(json.dumps({str(d):sha(d) for _,d in pairs},indent=2))
print('Source sync passed; before snapshots and exact diff retained')
