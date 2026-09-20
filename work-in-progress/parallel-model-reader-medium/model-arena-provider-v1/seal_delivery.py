import hashlib,json,pathlib,time
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2];B=R.parent/'model-arena-buft-v1'
pairs=[(P/'port/new/nuttx/arch/arm64/src/rk3576/rk3576_model_arena.c',R/'input/arena/rk3576_model_arena.c'),(P/'port/new/nuttx/include/nuttx/mm/k7_model_arena.h',R/'input/nuttx/mm/k7_model_arena.h')]
for name in ['k7_host_buft.h','k7_host_buft.cpp']:pairs.append((B/name,R/'input/buft'/name))
for target in (R/'input/include').glob('*'):pairs.append((B/'input/include'/target.name,target))
def row(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
inputs=[]
for source,target in pairs:
 assert source.read_bytes()==target.read_bytes(),str(source)+' changed after snapshot'
 x=row(source);x['snapshot']=str(target.relative_to(R));inputs.append(x)
L=P/'work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063440936377Z/build/llama/ggml/src'
inputs += [row(L/name) for name in ['ggml.a','ggml-cpu.a','ggml-base.a']]
inputs.append(row(B/'delivery.json'))
(R/'evidence/input-hashes.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
files=[]
for p in sorted(R.rglob('*')):
 if p.is_file() and p.name!='delivery.json':
  x=row(p);x['path']=str(p.relative_to(R));files.append(x)
(R/'delivery.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'target provider candidate; host mocked API protocol tests only','target_run':False,'model_loaded':False,'limit_bytes':1048576,'files':files},indent=2),encoding='utf-8')
for x in files:assert row(R/x['path'])['sha256']==x['sha256']
print('verified',len(files),'files; delivery sha256',row(R/'delivery.json')['sha256'])
