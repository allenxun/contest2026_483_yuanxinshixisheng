import re,base64,zlib,json
from pathlib import Path
w=Path('/home/swl/openvela/work/rk3576-preview')
raw=(w/'async-dry.log').read_bytes()
head=None;chunks=[];good=bad=0
for line in raw.splitlines():
 line=line.strip()
 m=re.search(rb'VIEW BEGIN q=(\d+) n=(\d+) crc=([0-9a-fA-F]{8})',line)
 if m:head=(int(m[1]),int(m[2]),int(m[3],16));chunks=[]
 elif head and line.startswith(b'V '):chunks.append(line[2:])
 elif head and line.startswith(b'VIEW END q='):
  try:
   b=base64.b64decode(b''.join(chunks),validate=True)
   assert len(b)==head[1] and zlib.crc32(b)==head[2]
   assert int(line.split(b'=')[-1])==head[0]
   good+=1
  except Exception:bad+=1
  head=None
summary=[x.decode(errors='replace') for x in raw.splitlines() if any(y in x for y in (b'TRACK END',b'PIPE ',b'YUNET ',b'UVC ISO END'))]
result={'valid_preview':good,'corrupt_preview':bad,'incomplete_at_end':head is not None,'summaries':summary}
(w/'async-dry-analysis.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
