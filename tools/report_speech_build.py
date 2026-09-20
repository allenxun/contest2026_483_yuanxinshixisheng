"""Audit, build or collect the stage-prompt candidate. No hardware access."""
import argparse,base64,difflib,hashlib,json
from cloud_radio_stage_audit import ROOT,remote
from audit_voice_mode_sdk import FILES as MOTION_FILES
FILES=['app/k7agent/cloud/src/board_speech_bridge.c','app/k7agent/cloud/src/k7cloud_main.c']
MOTION_FILES+=['app/k7agent/cloud/src/board_fixed_pcm.inc']
MOTION_FILES+=['app/k7agent/cloud/src/k7cloud_main.c','app/k7sound/pio.c','app/k7host/k7_photo.c','app/k7host/k7_photo_store.c','app/k7agent/cloud/src/board_speech_bridge.c','app/k7agent/cloud/src/device_photo_prompts.c']
REV='report-speech-20260917'
OUT=ROOT/'evidence'/REV
p=argparse.ArgumentParser();p.add_argument('mode',choices=['audit','build','collect']);args=p.parse_args()
OUT.mkdir(parents=True,exist_ok=True)
if args.mode=='audit':
    data=json.loads(remote('import pathlib,base64,json\nr=pathlib.Path("/home/swl/openvela/apps/examples")\nprint(json.dumps({p:base64.b64encode((r/p[4:]).read_bytes()).decode() if (r/p[4:]).exists() else None for p in %r}))'%FILES))
    hashes={};diff=[]
    for rel,value in data.items():
        old=base64.b64decode(value) if value is not None else b''
        dest=OUT/'sdk-before'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and dest.read_bytes()!=old:raise RuntimeError('Predecessor changed')
        dest.write_bytes(old);hashes[rel]=hashlib.sha256(old).hexdigest() if value is not None else None
        diff.extend(difflib.unified_diff(old.decode().replace('\r','').splitlines(True),(ROOT/rel).read_text(encoding='utf8').replace('\r','').splitlines(True),fromfile='sdk/'+rel,tofile=rel))
    (OUT/'sdk-before.json').write_text(json.dumps(hashes,indent=2)+'\n')
    (OUT/'sdk.diff').write_text(''.join(diff),encoding='utf8');print('Audited',len(FILES),'files; full diff saved locally')
elif args.mode=='build':
    baseline=json.loads((OUT/'sdk-before.json').read_text());assert set(baseline)==set(FILES)
    bp='evidence/sync/'+REV+'.json';(ROOT/bp).write_text(json.dumps(baseline,indent=2)+'\n')
    payload={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in FILES+[bp,'tools/sync_sdk.py']}
    print(remote('''import pathlib,base64,hashlib,subprocess
sdk=pathlib.Path('/home/swl/openvela');root=sdk/'work/velavision-project';ev=root/'evidence/report-speech-20260917'
assert not (ev/'build.log').exists(),'build already exists'
for rel,digest in %r.items():
 p=sdk/'apps/examples'/rel[4:]
 assert (hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None)==digest,rel
for rel,data in %r.items():
 p=root/rel;raw=base64.b64decode(data)
 if p.exists() and p.read_bytes()!=raw:
  old=p.read_bytes();before=ev/'project-before'/hashlib.sha256(old).hexdigest()/rel
  before.parent.mkdir(parents=True,exist_ok=True);before.write_bytes(old)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
cmd=['python3',str(root/'tools/sync_sdk.py'),'--sdk',str(sdk)]
for rel in %r:cmd+=['--include',rel]
for mode in ['--check','--apply','--check']:subprocess.check_call(cmd+[mode])
ev.mkdir(parents=True,exist_ok=True)
with (ev/'build.log').open('xb') as log:
 shell='source build/envsetup.sh >/dev/null && prebuilts/tools/cmake/bin/cmake -S nuttx -B cmake_out/velavision_report_speech_20260917 -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_photo_tcp && prebuilts/tools/cmake/bin/cmake --build cmake_out/velavision_report_speech_20260917 -j4; result=$?; echo $result > work/velavision-project/evidence/report-speech-20260917/build.exit; exit $result'
 child=subprocess.Popen(['bash','-c',shell],cwd=sdk,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('build_pid',child.pid)
'''%(baseline,payload,FILES)).decode())
else:
    data=json.loads(remote('''import pathlib,hashlib,base64,json
sdk=pathlib.Path('/home/swl/openvela');ev=sdk/'work/velavision-project/evidence/report-speech-20260917'
assert (ev/'build.exit').read_text().strip()=='0'
raw=(sdk/'cmake_out/velavision_report_speech_20260917/nuttx.bin').read_bytes()
assert all(s in raw for s in [b'VOICE SESSION ready mode=0',b'K7CLOUD prompt_started busy=1',b'K7CLOUD tts_state'])
print(json.dumps(dict(image=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),log=(ev/'build.log').read_text(errors='replace'),sources={p:hashlib.sha256((sdk/'apps/examples'/p[4:]).read_bytes()).hexdigest() for p in %r})))
'''%(FILES+MOTION_FILES)))
    raw=base64.b64decode(data.pop('image'));log=data.pop('log').encode()
    assert hashlib.sha256(raw).hexdigest()==data['sha256']
    for rel,digest in data['sources'].items():assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest,rel
    for name,content in [('nuttx.bin',raw),('build.log',log)]:
        dest=OUT/name
        if dest.exists() and dest.read_bytes()!=content:raise RuntimeError('Refuse overwrite')
        dest.write_bytes(content)
    data.update(build_exit_code=0,ram_loaded=False,hardware_tested=False)
    (OUT/'verification.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data,indent=2))


