from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[1];old=R.parent/'parallel-k7-audio'
manifest=json.loads((old/'evidence/linux-inputs.json').read_text(encoding='utf8'))
for row in manifest:
 p=old/'sources'/row['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
 p2=R/'input'/row['path'];p2.parent.mkdir(parents=True,exist_ok=True)
 # 14 small selected blobs only (557790 bytes), no models or SDK workspace.
 with p2.open('xb') as f:f.write(p.read_bytes())
 row['source']=str(p)
for name in ['HARDWARE.md','PLAN.md','HANDOFF.md']:
 p=old/name;data=p.read_bytes()
 with (R/'input'/name).open('xb') as f:f.write(data)
 manifest.append({'source':str(p),'path':name,'sha256':hashlib.sha256(data).hexdigest()})
(R/'input/sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
print('source_snapshot_count',len(manifest),'all_fixed_blob_hashes_verified')
