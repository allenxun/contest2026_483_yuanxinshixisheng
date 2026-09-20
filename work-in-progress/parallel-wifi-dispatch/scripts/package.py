from pathlib import Path
import difflib,hashlib,json
R=Path(__file__).resolve().parents[1]
patch=[]
for name in ('include/wifi_dispatch.h','src/wifi_dispatch.c','tests/test_dispatch.c'):
    patch.extend(difflib.unified_diff([], (R/name).read_text(encoding='utf8').splitlines(True),
                                     fromfile='/dev/null',tofile='b/'+name))
name='src/wifi_broker.c'
patch.extend(difflib.unified_diff((R/'input'/name).read_text(encoding='utf8').splitlines(True),
                                (R/name).read_text(encoding='utf8').splitlines(True),
                                fromfile='a/'+name,tofile='b/'+name))
(R/'candidate.patch').write_text(''.join(patch),encoding='utf8',newline='\n')
rows=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
      for p in sorted(R.rglob('*')) if p.is_file() and p.name!='delivery.json' and '__pycache__' not in p.parts]
(R/'delivery.json').write_text(json.dumps(dict(session_id='01a0892e-2964-7ec3-bd76-9ab4937980cb',files=rows),ensure_ascii=False,indent=2),encoding='utf8')
print('delivery_files',len(rows))
