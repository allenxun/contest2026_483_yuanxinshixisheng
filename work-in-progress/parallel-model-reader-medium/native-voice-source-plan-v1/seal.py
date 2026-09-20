from pathlib import Path
import hashlib,json
p=Path(__file__).parent;r=Path('E:/openvela/VelaVision');h=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
local=['app/k7agent/model_reader/model_reader.h','port/new/nuttx/include/nuttx/mm/k7_model_arena.h','work-in-progress/parallel-model-reader-medium/native-voice-runtime-audit-v1/inputs.json']
(p/'local-inputs.json').write_text(json.dumps([{'path':n,'sha256':h(r/n)} for n in local],indent=2))
a=[{'path':str(f.relative_to(p)).replace('\\','/'),'sha256':h(f)} for f in sorted(p.rglob('*')) if f.is_file() and f.name not in ['outputs.json','delivery.json']]
(p/'outputs.json').write_text(json.dumps(a,indent=2));(p/'delivery.json').write_text(json.dumps({'status':'PINNED_NATIVE_SOURCE_PLAN_NOT_BUILD_VERIFIED','outputs_sha256':h(p/'outputs.json'),'sources_sha256':h(p/'sources.json')},indent=2))
for x in a:assert h(p/x['path'])==x['sha256']
for n in ['delivery.json','outputs.json','sources.json']:print(n,h(p/n))
print('Verified',len(a),'files')
