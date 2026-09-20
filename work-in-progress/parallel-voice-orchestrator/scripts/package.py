from pathlib import Path
import hashlib,json,difflib
R=Path(__file__).resolve().parents[1]
patch=[]
for folder in ['include','src','tests','scripts']:
 for p in sorted((R/folder).rglob('*')):
  if not p.is_file() or p.suffix not in ['.hpp','.h','.c','.cpp','.py']:continue
  rel=p.relative_to(R).as_posix();old=R/'input'/rel
  patch.extend(difflib.unified_diff(old.read_text(encoding='utf8').splitlines(True) if old.exists() else [],p.read_text(encoding='utf8').splitlines(True),fromfile='a/'+rel if old.exists() else '/dev/null',tofile='b/'+rel))
(R/'candidate.patch').write_text(''.join(patch),encoding='utf8')
inputs=json.loads((R/'input/sources.json').read_text(encoding='utf8'))
for row in inputs:row['unchanged']=hashlib.sha256(Path(row['source']).read_bytes()).hexdigest()==row['sha256']
delivery={'session_id':'01a0892e-2964-7ec3-bd76-9ab4937980cb','cwd':r'E:\openvela','inputs':inputs,
 'files':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(R.rglob('*')) if p.is_file() and p.name!='delivery.json'},
 'board_verified':False,'agent_deployed':False,'log_collection_owner':'main thread; maomaojiang01'}
(R/'evidence/delivery.json').write_text(json.dumps(delivery,ensure_ascii=False,indent=2),encoding='utf8')
print('inputs_unchanged',all(x['unchanged'] for x in inputs),'files',len(delivery['files']))
