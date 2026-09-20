import hashlib,json,pathlib,time
R=pathlib.Path(__file__).resolve().parent
P=R.parents[2]
B=P/'work-in-progress/parallel-llama-b0/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/examples/gguf-hash/deps'
pairs=[]
for name in ['model_reader.c','model_reader.h']:
 pairs.append((P/'app/k7agent/model_reader'/name,R/'input/formal'/name))
 pairs.append((R.parent/name,R/'input/original'/name))
for group,names in [('sha256',['sha256.c','sha256.h','package.json']),('rotate-bits',['rotate-bits.h','package.json'])]:
 for name in names:pairs.append((B/group/name,R/'vendor'/group/name))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs=[]
for origin,snapshot in pairs:
 assert sha(origin)==sha(snapshot),str(origin)+' changed since snapshot; do not silently refresh'
 inputs.append({'origin':str(origin),'snapshot':str(snapshot.relative_to(R)),'bytes':snapshot.stat().st_size,'sha256':sha(snapshot)})
(R/'evidence/input-hashes.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
files=[]
for p in sorted(R.rglob('*')):
 if p.is_file() and p.name!='delivery.json':files.append({'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p)})
(R/'delivery.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'status':'host-tested integrity candidate','nuttx_tested':False,'model_loaded':False,'hardware_accessed':False,'same_length_mutation_not_prevented':True,'files':files},indent=2),encoding='utf-8')
print('sealed',len(files),'files; delivery sha256',sha(R/'delivery.json'))
