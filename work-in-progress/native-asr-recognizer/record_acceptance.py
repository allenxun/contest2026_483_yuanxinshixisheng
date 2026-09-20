import json,re,hashlib,datetime
from pathlib import Path
r=Path(__file__).resolve().parent;project=r.parents[1]
p=r/'probe-20260911-174831.log';raw=p.read_text()
result=re.search(r'ASR_INFER RESULT seconds=([0-9.]+) text=(.*)',raw)
stats=re.search(r'ASR_STORAGE peak=(\d+) live=(\d+) records=(\d+) failures=(\d+) reason=(\d+)',raw)
assert result and stats and tuple(map(int,stats.groups()[1::2]))==(0,0)
accept={'firmware_sha256':'b98b29e8f365cdc61c07cc8bcdf704aec48758bf4db5f1a14fa7dfc027e946f1','fixed_wav_recognized':True,'seconds_including_model_load':float(result[1]),'text':result[2],'model_pool_peak_bytes':int(stats[1]),'model_pool_live_after_cleanup':int(stats[2]),'peak_records':int(stats[3]),'allocation_failures':int(stats[4]),'microphone_recognition_verified':False,'voice_wifi_verified':False,'log_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'log':str(p.relative_to(project))}
(r/'acceptance.json').write_text(json.dumps(accept,ensure_ascii=False,indent=2),encoding='utf-8')
m=project/'project-manifest.json';obj=json.loads(m.read_text(encoding='utf-8-sig'))
obj['current_device']['asr_inference_status']='fixed WAV passed; microphone and provisioning pending'
obj['current_device']['asr_acceptance']=accept
obj['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
m.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(accept,ensure_ascii=False))
