from pathlib import Path
import hashlib,json,urllib.request
p=Path(__file__).parent;r=Path('E:/openvela/VelaVision');(p/'input').mkdir(exist_ok=True)
fs=['work-in-progress/parallel-model-reader-medium/native-voice-source-plan-v1/sources/ort-env.txt','work-in-progress/parallel-model-reader-medium/native-voice-source-plan-v1/sources/ort-platform.txt','evidence/model-file-vfs-inputs-20260910/nuttx/include/unistd.h','evidence/model-file-vfs-inputs-20260910/nuttx/include/sys/stat.h','app/k7radio/radio_backend.inc','app/k7radio/k7radio_main.c','app/k7agent/model_reader/model_reader.c']
a=[]
for i,n in enumerate(fs):
 b=(r/n).read_bytes();name=f'{i:02d}-'+Path(n).name;(p/'input'/name).write_bytes(b);a.append({'path':n,'snapshot':'input/'+name,'sha256':hashlib.sha256(b).hexdigest()})
for name in ['pthread.h','time.h']:
 url='https://raw.githubusercontent.com/open-vela/nuttx/e987a81c32cab008d1a8521669e5488d00271322/include/'+name
 try:
  with urllib.request.urlopen(url,timeout=15) as f:b=f.read(200001)
  assert len(b)<=200000;(p/'input'/name).write_bytes(b);a.append({'url':url,'snapshot':'input/'+name,'sha256':hashlib.sha256(b).hexdigest()})
 except Exception as e:a.append({'url':url,'error':str(e)})
(p/'inputs.json').write_text(json.dumps(a,indent=2));print([(x.get('snapshot'),x.get('error')) for x in a])
