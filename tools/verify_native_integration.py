"""Record software-only integrated checks, preserving failures and source hashes."""
import os,json,subprocess,sys,hashlib
from pathlib import Path
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[1]
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out=root/'evidence/native-photo-prompts-20260915'/('tests-'+stamp)
out.mkdir(parents=True,exist_ok=False)
tests=['test_device_intent_vm.py','test_device_stop_vm.py','test_photo_store_vm.py',
       'test_native_photo_flow_vm.py','test_photo_prompts_vm.py','test_voice_mode_vm.py']
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
results=[]
for name in tests:
    result=subprocess.run([sys.executable,str(root/'tools'/name)],cwd=root,env=env,
                          capture_output=True,timeout=90)
    (out/(name+'.stdout')).write_bytes(result.stdout)
    (out/(name+'.stderr')).write_bytes(result.stderr)
    results.append({'tool':name,'exit_code':result.returncode})
    print(name,result.returncode,flush=True)
    if result.returncode:break
paths=list((root/'app/k7agent/cloud').rglob('device_*.*'))
paths+=[root/'app/k7agent/cloud/src/board_speech_bridge.c']
paths+=list((root/'app/k7host').glob('k7_photo*.*'))
report={'created_utc':stamp,'hardware_tested':False,'tests':results,
        'passed':len(results)==len(tests) and all(r['exit_code']==0 for r in results),
        'sources':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(out)
if not report['passed']:raise SystemExit(1)
