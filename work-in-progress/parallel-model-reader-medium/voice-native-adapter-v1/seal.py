from pathlib import Path
import hashlib,json,difflib
p=Path(__file__).parent;h=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
patch=''
for n in ['voice_wifi_adapter.cpp','voice_wifi_adapter.hpp']:
 patch+=''.join(difflib.unified_diff((p/('old-'+n)).read_text().splitlines(True),(p/'candidate'/n).read_text().splitlines(True),fromfile='old/'+n,tofile='candidate/'+n))
(p/'adapter-delta.patch').write_text(patch)
a=[{'path':str(f.relative_to(p)).replace('\\','/'),'sha256':h(f)} for f in sorted(p.rglob('*')) if f.is_file() and f.name not in ['outputs.json','delivery.json']]
(p/'outputs.json').write_text(json.dumps(a,indent=2));(p/'delivery.json').write_text(json.dumps({'status':'HOST_ADAPTER_COMPILED_NOT_TARGET_ACCEPTANCE','outputs_sha256':h(p/'outputs.json'),'after_inputs_sha256':h(p/'after-inputs.json')},indent=2))
for x in a:assert h(p/x['path'])==x['sha256']
for n in ['delivery.json','outputs.json','candidate/voice_wifi_adapter.cpp','candidate/voice_wifi_adapter.hpp']:print(n,h(p/n))
print('Verified',len(a),'files')
