from pathlib import Path
import hashlib
import json
import subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
inputs=['artifacts/cxx-eh-20260910/nuttx','artifacts/cxx-eh-20260910/.config',
        'app/k7eh/k7eh_main.cxx','evidence/cxx-eh-20260910/integration.json',
        'evidence/cxx-eh-20260910/cold/runtime.bin','evidence/cxx-eh-20260910/cold/runtime.json',
        'evidence/cxx-eh-20260910/cold/post-failure-ps.bin',
        'evidence/build/cxx-eh-20260910/unwind-audit.json',
        'work-in-progress/parallel-cxx-unwind-medium/THREADING-RISK.md']
hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}
records=[]
for opts,name in [(['--debug-dump=frames'],'frames.txt'),(['-sW'],'symbols.txt')]:
    cmd=['readelf']+opts+[str(ROOT/inputs[0])]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (HERE/name).write_bytes(p.stdout)
    records.append({'command':cmd,'exit_code':p.returncode,'output':name,'output_sha256':hashlib.sha256(p.stdout).hexdigest()})
assert hashes=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}
(HERE/'evidence.json').write_text(json.dumps({'input_sha256':hashes,'commands':records,
    'independent_hardware_access':False,'cause_established':False,'normal_join_proven':False},indent=2),encoding='utf-8')
