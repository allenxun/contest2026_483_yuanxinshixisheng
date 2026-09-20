from pathlib import Path
import hashlib,json,difflib
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rows=json.loads((R/'input/sources.json').read_text(encoding='utf8'))
for row in rows:row['unchanged']=sha(Path(row['source']))==row['sha256']
diff=[]
for directory in ['include','src','tests','scripts']:
 for p in sorted((R/directory).glob('*')):
  if p.is_file():diff.extend(difflib.unified_diff([],p.read_text(encoding='utf8').splitlines(True),fromfile='/dev/null',tofile='b/'+p.relative_to(R).as_posix()))
(R/'candidate.patch').write_text(''.join(diff),encoding='utf8')
d=dict(session_id='01a0892e-2964-7ec3-bd76-9ab4937980cb',cwd=r'E:\openvela',
 input_sources=rows,default_hardware_plan='KC_NOT_READY; no I/O',board_validated=False,
 files={str(p.relative_to(R)):sha(p) for p in sorted(R.rglob('*')) if p.is_file() and p.name!='delivery.json' and '__pycache__' not in p.parts})
(R/'evidence/delivery.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
print('inputs_unchanged',all(x['unchanged'] for x in rows),'files',len(d['files']))
