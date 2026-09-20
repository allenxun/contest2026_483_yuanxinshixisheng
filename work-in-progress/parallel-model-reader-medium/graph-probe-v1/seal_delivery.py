import hashlib,json,pathlib,time
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
POOL=P/'work-in-progress/parallel-llama-pool-safety';B=P/'work-in-progress/parallel-llama-b0/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5'
BUILD=POOL/'evidence/run-20260910T063440936377Z'
inputs=[POOL/x for x in ['candidate/ggml-cpu.c','candidate/ggml-backend-reg.cpp','candidate/LICENSE','include/ggml-pool-safe.h','tests/pool.c','CONTRACT.md','HANDOFF.md','CMakeLists.txt','delivery.json','source-manifest.json']]
inputs += [BUILD/x for x in ['audit.json','inputs.json','commands.json','build/CMakeFiles/pool-test.dir/linkLibs.rsp']]
inputs += [BUILD/'build/llama/ggml/src'/x for x in ['ggml.a','ggml-cpu.a','ggml-base.a']]
inputs += [B/x for x in ['LICENSE','ggml/src/ggml.c','ggml/src/ggml-cpu/ggml-cpu.c']]
for p in (R/'input/include').glob('*.h'):
 origin=POOL/'include'/p.name if p.name=='ggml-pool-safe.h' else B/'ggml/include'/p.name
 assert p.read_bytes()==origin.read_bytes(),str(origin)+' changed'
 inputs.append(origin)
def row(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
# Verify pool candidate inputs against its existing delivery, not just current hashes.
prior=json.loads((POOL/'delivery.json').read_text(encoding='utf-8'))
for item in prior['files']:
 p=POOL/item['path']
 if p in inputs:assert row(p)['sha256']==item['sha256'],str(p)+' differs from frozen delivery'
(R/'evidence/input-hashes.json').write_text(json.dumps([row(p) for p in inputs],indent=2),encoding='utf-8')
files=[]
for p in sorted(R.rglob('*')):
 if p.is_file() and p.name!='delivery.json':
  item=row(p);item['path']=str(p.relative_to(R));files.append(item)
d={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'real checked ggml CPU graph host tested; NuttX integration pending','weights':False,'hardware_tested':False,'affinity_integrated':False,'files':files}
(R/'delivery.json').write_text(json.dumps(d,indent=2),encoding='utf-8')
for item in files:
 p=R/item['path'];assert row(p)['sha256']==item['sha256']
print('verified',len(files),'files; delivery sha256',row(R/'delivery.json')['sha256'])
