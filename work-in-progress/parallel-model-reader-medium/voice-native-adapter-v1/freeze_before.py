from pathlib import Path
import hashlib,json
r=Path('E:/openvela/VelaVision');p=r/'work-in-progress/parallel-model-reader-medium/voice-native-adapter-v1'
paths=list((r/'app/k7radio').glob('wifi_*.h'))+list((r/'app/k7radio').glob('wifi_*.c'))+[r/'app/k7radio'/n for n in ['scan_contract.h','scan_collector.h','scan_collector.c','k7_radio_service.h','radio_backend.inc']]+list((r/'app/voicelink/include/voicelink').glob('*.hpp'))+list((r/'app/voicelink/src').glob('*.cpp'))
a=[]
for f in paths:
 n=f.relative_to(r);q=p/'before'/n;q.parent.mkdir(parents=True,exist_ok=True);b=f.read_bytes();q.write_bytes(b);a.append({'path':str(n),'sha256':hashlib.sha256(b).hexdigest()})
(p/'before-inputs.json').write_text(json.dumps(a,indent=2));print('frozen',len(a))
