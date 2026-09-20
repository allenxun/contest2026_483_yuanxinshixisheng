import pathlib,hashlib,json
ROOT=pathlib.Path(__file__).resolve().parent
PROJECT=ROOT.parents[2]
B='work-in-progress/parallel-model-reader-medium/'
provider=B+'model-arena-provider-v1/'
buft=B+'model-arena-buft-v1/'
vendor='work-in-progress/parallel-llama-pool-safety/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/src/'
paths=[provider+p for p in ['k7_target_provider.c','k7_target_provider.h','k7_arena_diagnostic.c','k7_arena_diagnostic.h','k7_arena_provider_main.c','HANDOFF.md','evidence/host-tests.json','input/arena/rk3576_model_arena.c','input/nuttx/mm/k7_model_arena.h','input/buft/k7_host_buft.cpp','input/buft/k7_host_buft.h']]
paths += [buft+p for p in ['k7_host_buft.cpp','k7_host_buft.h','HANDOFF.md','evidence/host-tests.json']]
paths += ['port/new/nuttx/arch/arm64/src/rk3576/rk3576_model_arena.c','port/new/nuttx/include/nuttx/mm/k7_model_arena.h']
paths += [vendor+p for p in ['ggml-alloc.c','ggml-backend.cpp','ggml.c']]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
hashes={p:sha(PROJECT/p) for p in paths}
pairs=[('port/new/nuttx/arch/arm64/src/rk3576/rk3576_model_arena.c',provider+'input/arena/rk3576_model_arena.c'),('port/new/nuttx/include/nuttx/mm/k7_model_arena.h',provider+'input/nuttx/mm/k7_model_arena.h'),(buft+'k7_host_buft.cpp',provider+'input/buft/k7_host_buft.cpp'),(buft+'k7_host_buft.h',provider+'input/buft/k7_host_buft.h')]
comparison=[dict(left=a,right=b,identical=hashes[a]==hashes[b]) for a,b in pairs]
tests=[]
for p in [buft+'evidence/host-tests.json',provider+'evidence/host-tests.json']:
 data=json.loads((PROJECT/p).read_text(encoding='utf-8'))
 rows=data.get('results',[])
 tests.append(dict(path=p,existing_commands=len(rows),returncodes=[r.get('returncode') for r in rows],independently_rerun=False))
(ROOT/'inputs.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
(ROOT/'verification.json').write_text(json.dumps(dict(scope='read-only identities and existing evidence; no compilation/execution',comparisons=comparison,existing_tests=tests),indent=2)+'\n',encoding='utf-8')
(ROOT/'hashes.json').write_text(json.dumps({p.name:sha(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='hashes.json'},indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(comparisons=comparison,existing_tests=tests),indent=2))
