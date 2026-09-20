import hashlib,json
from pathlib import Path
H=Path(__file__).resolve().parent; R=H.parents[2]
E=R/'evidence/native-speech-ort-conversion1-20260911'
O=R/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
paths=[E/x for x in ('asr-required.config','encoder.json','decoder.json','encoder.log','decoder.log','result.json')]
paths += [O/x for x in ('tools/ci_build/reduce_op_kernels.py','cmake/onnxruntime_providers.cmake','cmake/onnxruntime_providers_cpu.cmake')]
paths += [R/'tools/configure_native_ort_session9.py',H.parent/'native-ort-cmake-nuttx-v1/initial-cache.cmake']
records=[]
for n in ('encoder','decoder'):
 d=json.loads((E/(n+'.json')).read_text());p=Path(d['output'])
 assert d['ort_version']=='1.17.1' and d['optimization']=='ORT_DISABLE_ALL'
 actual=sha(p);assert actual==d['output_sha256']
 records.append(dict(model=n,path=str(p),sha256=actual,bytes=p.stat().st_size,conversion_only=True))
data=(E/'asr-required.config').read_bytes();(H/'asr-required.config').write_bytes(data)
rows=[]
for line in data.decode().splitlines():
 if not line or line.startswith('#'):continue
 domain,version,ops=line.split(';');rows.append(dict(domain=domain,version=int(version),ops=ops.split(',')))
assert all('StringNormalizer' not in r['ops'] for r in rows)
(H/'verification.json').write_text(json.dumps(dict(models=records,rows=rows,operator_entries=sum(len(r['ops']) for r in rows),StringNormalizer=False,target_run=False),indent=2))
(H/'inputs.json').write_text(json.dumps({str(p):sha(p) for p in paths},indent=2))
print('conversion outputs verified; operator entries',sum(len(r['ops']) for r in rows))
