from pathlib import Path
import hashlib,json,difflib,datetime
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
patch=[]
for name in ['audio_candidate.py','test_candidate.py']:
 patch.extend(difflib.unified_diff([], (R/name).read_text(encoding='utf8').splitlines(True),fromfile='/dev/null',tofile='b/'+name))
(R/'candidate.patch').write_text(''.join(patch),encoding='utf8')
pdf=json.loads((R/'evidence/pdf-inputs.json').read_text(encoding='utf8'))
for row in pdf:row['unchanged']=sha(Path(row['path']))==row['sha256']
latest=sorted((R/'evidence').glob('run-*'))[-1]
project=json.loads((latest/'project-inputs.json').read_text(encoding='utf8'))
for row in project:row['unchanged']=sha(Path(row['source']))==row['sha256']
src=Path(r'E:\openvela\无线适配_2026-09-08\official-linux-20260320')
source_meta=[dict(path=str(src/name),sha256=sha(src/name)) for name in ['tree.json','commit.txt','archive-verified.json']]
delivery=dict(session_id='01a0892e-2964-7ec3-bd76-9ab4937980cb',cwd=r'E:\openvela',
 board_tested=False,inputs_pdf=pdf,inputs_project=project,official_source=source_meta,
 files={str(p.relative_to(R)):sha(p) for p in sorted(R.rglob('*')) if p.is_file() and p.name!='delivery.json' and '__pycache__' not in p.parts})
(R/'evidence/delivery.json').write_text(json.dumps(delivery,ensure_ascii=False,indent=2),encoding='utf8')
print('input_unchanged',all(x['unchanged'] for x in pdf+project),'files',len(delivery['files']))
