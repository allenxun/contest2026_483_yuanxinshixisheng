import pathlib,json,hashlib,time
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
V=P/'work-in-progress/parallel-llama-b0/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5'
paths=[]
for p in (R/'input/include').glob('*'):
 source=V/('ggml/src' if p.name=='ggml-backend-impl.h' else 'ggml/include')/p.name
 assert p.read_bytes()==source.read_bytes();paths.append(source)
paths += [V/x for x in ['ggml/src/ggml-backend.cpp','ggml/src/ggml-cpu/ggml-cpu.cpp','ggml/src/ggml-alloc.c','LICENSE']]
paths += [R.parent/'model-arena-plan-v1'/x for x in ['arena_buffer_lease.cpp','arena_buffer_lease.h','HANDOFF.md','delivery.json']]
L=P/'work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063440936377Z/build/llama/ggml/src'
paths += [L/x for x in ['ggml.a','ggml-cpu.a','ggml-base.a']]
def row(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
(R/'evidence/input-hashes.json').write_text(json.dumps([row(p) for p in paths],indent=2),encoding='utf-8')
files=[]
for p in sorted(R.rglob('*')):
 if p.is_file() and p.name!='delivery.json':
  x=row(p);x['path']=str(p.relative_to(R));files.append(x)
(R/'delivery.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'explicit host buft candidate; real ggml host tests; fake provider','target_arena_tested':False,'models_loaded':False,'files':files},indent=2),encoding='utf-8')
for x in files:assert row(R/x['path'])['sha256']==x['sha256']
print('verified',len(files),'files; delivery sha256',row(R/'delivery.json')['sha256'])
