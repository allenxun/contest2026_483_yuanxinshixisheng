"""Fetch upstream GCC 13.4 reference sources; not asserted as SDK build inputs."""
import hashlib,json,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/gcc-unwind-reference-20260910';E.mkdir(exist_ok=True)
base='https://raw.githubusercontent.com/gcc-mirror/gcc/releases/gcc-13.4.0/'
names=['libgcc/unwind-dw2.c','libgcc/unwind-dw2-fde.c','libgcc/unwind-dw2-fde.h','libgcc/unwind.inc','libgcc/gthr-posix.h','libgcc/gthr-single.h']
records=[]
for name in names:
 url=base+name;p=E/Path(name).name
 assert not p.exists()
 try:
  with urllib.request.urlopen(url,timeout=30) as response:data=response.read(2000000)
  p.write_bytes(data)
  records.append(dict(url=url,path=p.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
 except Exception as exc:
  records.append(dict(url=url,error=type(exc).__name__,message=str(exc)))
with (E/'sources.json').open('x',encoding='utf-8') as f:json.dump(dict(scope='Upstream release reference, not proof of local SDK exact source/configuration',sources=records),f,indent=2)
print(json.dumps([dict(path=x.get('path'),bytes=x.get('bytes'),error=x.get('error')) for x in records]))
