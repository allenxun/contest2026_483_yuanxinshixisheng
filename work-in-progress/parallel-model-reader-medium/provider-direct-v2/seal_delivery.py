import pathlib,json,hashlib,difflib,time
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2];OLD=R.parent/'model-arena-provider-v1'
V=P/'work-in-progress/parallel-llama-b0/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5'
changed='k7_arena_diagnostic.c'
patch=''.join(difflib.unified_diff((OLD/changed).read_text().splitlines(True),(R/changed).read_text().splitlines(True),fromfile='a/'+changed,tofile='b/'+changed))
(R/'diagnostic-direct-v2.patch').write_text(patch,encoding='utf-8')
def row(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
inputs=[row(OLD/changed),row(OLD/'delivery.json'),row(V/'ggml/src/ggml-backend.cpp'),row(V/'ggml/src/ggml-alloc.c')]
for p in R.rglob('*'):
 if p.is_file() and (p.relative_to(R).parts[0] in ['input','host-mock'] or p.name in ['k7_target_provider.c','k7_target_provider.h','k7_arena_diagnostic.h','k7_arena_provider_main.c']):
  old=OLD/p.relative_to(R);assert old.read_bytes()==p.read_bytes(),str(p)+' unexpectedly changed';inputs.append(row(old))
L=P/'work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063440936377Z/build/llama/ggml/src'
inputs += [row(L/name) for name in ['ggml.a','ggml-cpu.a','ggml-base.a']]
(R/'evidence/input-hashes.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
files=[]
for p in sorted(R.rglob('*')):
 if p.is_file() and p.name!='delivery.json':
  x=row(p);x['path']=str(p.relative_to(R));files.append(x)
(R/'delivery.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'direct single-buffer diagnostic; host mock API + real ggml tested','target_run':False,'ggml_init_oom_abort_fixed':False,'files':files},indent=2),encoding='utf-8')
for x in files:assert row(R/x['path'])['sha256']==x['sha256']
print('verified',len(files),'files; delivery sha256',row(R/'delivery.json')['sha256'])
print('diagnostic sha256',row(R/changed)['sha256'])
