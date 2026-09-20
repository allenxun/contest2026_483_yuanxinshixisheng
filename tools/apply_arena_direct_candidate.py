"""Replace only staged diagnostic after frozen v2 review; preserve both origins."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];C=R/'work-in-progress/parallel-model-reader-medium/provider-direct-v2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(C/'delivery.json')=='81c539c6474e06101522b79139945bb0b6b318f2f1f6921d78940ee568344bd6'
for x in json.loads((C/'delivery.json').read_text())['files']:assert sha(C/x['path'])==x['sha256']
E=R/'evidence/arena-provider-20260910';p=E/'integration.json';m=json.loads(p.read_text())
target=R/'app/k7arena/k7_arena_diagnostic.c';old=m['files']['k7_arena_diagnostic.c']
assert sha(target)==old['sha256']
new=C/'k7_arena_diagnostic.c';assert sha(new)=='c05874a7ae3367efb394915a22d1c71f7f5aa2b88b4a5b355813601a2c98b835'
target.write_bytes(new.read_bytes())
m['superseded_diagnostic']=old;m['files']['k7_arena_diagnostic.c']=dict(source=str(new.relative_to(R)),sha256=sha(new))
m['direct_v2_delivery_sha256']=sha(C/'delivery.json');m['reason']='Fixed single-buffer placement avoids unchecked upstream realloc helper'
p.write_text(json.dumps(m,indent=2)+'\n')
print('Applied only reviewed direct-buffer diagnostic; original candidate provenance retained')
