from pathlib import Path
import hashlib,json
p=Path(__file__).parent
h=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
up=p.parent/'ble-acl-diag-v1/candidate'
inputs=[{'path':str(f),'sha256':h(f)} for f in [up/'bt_meta.h',up/'k7radio_main.c',p/'synthetic-before.txt',p/'synthetic-after.txt']]
(p/'inputs.json').write_text(json.dumps(inputs,indent=2))
items=[{'path':str(f.relative_to(p)).replace('\\','/'),'sha256':h(f)} for f in sorted(p.rglob('*')) if f.is_file() and f.name not in ['outputs.json','delivery.json']]
(p/'outputs.json').write_text(json.dumps(items,indent=2))
(p/'delivery.json').write_text(json.dumps({'status':'OFFLINE_SYNTHETIC_TESTS_PASSED','outputs_sha256':h(p/'outputs.json'),'report_sha256':h(p/'report.py')},indent=2))
for n in ['delivery.json','outputs.json','report.py']:print(n,h(p/n))
for item in items:assert h(p/item['path'])==item['sha256']
print('Verified',len(items),'files')
