from pathlib import Path
import urllib.request,hashlib,json,tarfile,zipfile,io,time
p=Path(__file__).parent
specs=[('kaldifst','https://github.com/k2-fsa/kaldifst/archive/refs/tags/v1.7.17.tar.gz','c4b701a23a400bda8032586b02c7e0d5e813a765832df60c23e6df9e62b010f4'),('openfst','https://github.com/csukuangfj/openfst/archive/refs/tags/sherpa-onnx-2024-06-19.tar.gz','5c98e82cc509c5618502dde4860b8ea04d843850ed57e6d6b590b644b268853d')]
rows=[]
for name,url,digest in specs:
 row={'name':name,'url':url,'expected_sha256':digest}
 try:
  start=time.monotonic();parts=[];size=0
  with urllib.request.urlopen(url,timeout=25) as r:
   while True:
    b=r.read(1024*1024)
    if not b:break
    size+=len(b);assert size<40*1024*1024 and time.monotonic()-start<90;parts.append(b)
  data=b''.join(parts);actual=hashlib.sha256(data).hexdigest();assert actual==digest,('HASH_MISMATCH',actual)
  ext='.zip' if url.endswith('.zip') else '.tar.gz';(p/(name+ext)).write_bytes(data);snap=[]
  if ext=='.zip':
   z=zipfile.ZipFile(io.BytesIO(data));items=[(n,z.read(n)) for n in z.namelist() if n.endswith(('CMakeLists.txt','.cmake'))]
  else:
   with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as t:items=[(m.name,t.extractfile(m).read()) for m in t if m.isfile() and m.name.endswith(('CMakeLists.txt','.cmake')) and m.size<2*1024*1024]
  for n,b in items:
   dst=p/'cmake-snapshots'/n;assert dst.resolve().is_relative_to(p.resolve());dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b);snap.append({'path':n,'sha256':hashlib.sha256(b).hexdigest()})
  row.update(status='VERIFIED',sha256=actual,bytes=size,snapshots=snap)
 except Exception as e:row.update(status='FAILED',error=repr(e))
 rows.append(row);(p/'download-results.json').write_text(json.dumps(rows,indent=2));print(name,row['status'],row.get('error',''),flush=True)

