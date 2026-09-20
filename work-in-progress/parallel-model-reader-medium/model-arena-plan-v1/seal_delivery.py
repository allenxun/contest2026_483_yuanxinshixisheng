import pathlib,hashlib,json,time
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
V=P/'work-in-progress/parallel-llama-b0/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5'
paths=[P/x for x in ['port/new/nuttx/include/nuttx/mm/k7_model_arena.h','port/new/nuttx/arch/arm64/src/rk3576/rk3576_model_arena.c','port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c','app/k7mem/k7mem_main.c','app/k7agent/model_reader/model_reader.c','app/k7agent/model_reader/model_reader.h','work-in-progress/parallel-model-reader-medium/integrity-v1/model_integrity.c','work-in-progress/parallel-model-reader-medium/integrity-v1/model_integrity.h']]
paths += [V/x for x in ['src/llama-model-loader.cpp','src/llama-mmap.cpp','src/llama-model.cpp','src/llama-kv-cache.cpp','src/llama-kv-cache.h','src/llama-context.cpp','src/llama-context.h','src/llama-impl.h','include/llama.h','ggml/src/ggml-backend.cpp','ggml/src/ggml-backend-impl.h','ggml/src/ggml-cpu/ggml-cpu.cpp','ggml/src/ggml-alloc.c','ggml/src/gguf.cpp','ggml/include/ggml-backend.h','ggml/include/ggml.h','ggml/include/ggml-alloc.h']]
L=P/'work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063440936377Z/build/llama/ggml/src'
paths += [L/x for x in ['ggml.a','ggml-cpu.a','ggml-base.a']]
def row(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
(R/'evidence/input-hashes.json').write_text(json.dumps([row(p) for p in paths],indent=2),encoding='utf-8')
files=[]
for p in sorted(R.rglob('*')):
 if p.is_file() and p.name!='delivery.json':
  x=row(p);x['path']=str(p.relative_to(R));files.append(x)
(R/'delivery.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'read-only allocation audit + host ownership helper','target_arena_tested':False,'llama_model_loaded':False,'selectable_k7_buft_implemented':False,'files':files},indent=2),encoding='utf-8')
for x in files:assert row(R/x['path'])['sha256']==x['sha256']
print('verified',len(files),'files; delivery sha256',row(R/'delivery.json')['sha256'])
