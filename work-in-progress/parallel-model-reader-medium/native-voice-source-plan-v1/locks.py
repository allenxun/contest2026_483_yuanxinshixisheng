from pathlib import Path
import json,re,hashlib
p=Path(__file__).parent
out=[]
for f in sorted((p/'sources').glob('dep-*.txt')):
 s=f.read_text();out.append({'source':f.name,'urls':re.findall(r'https://[^\s"\)]+',s),'sha256':re.findall(r'SHA256=([a-f0-9]{64})',s)})
(p/'sherpa-dependency-lock.json').write_text(json.dumps(out,indent=2))
