from pathlib import Path
import urllib.request,hashlib,json,tarfile,zipfile,io,time
p=Path(__file__).parent
specs=[('openfst','https://github.com/csukuangfj/openfst/archive/refs/tags/sherpa-onnx-2024-06-13.tar.gz','f10a71c6b64d89eabdc316d372b956c30c825c7c298e2f20c780320e8181ffb6'),('kissfft','https://github.com/mborgerding/kissfft/archive/febd4caeed32e33ad8b2e0bb5ea77542c40f18ec.zip','497103e664168ebe39580b757adbe616f6cf85a16572af581ca7bc42d0ab13fd'),('ssentencepiece','https://github.com/pkufool/simple-sentencepiece/archive/refs/tags/v0.7.tar.gz','1748a822060a35baa9f6609f84efc8eb54dc0e74b9ece3d82367b7119fdc75af'),('cppjieba','https://github.com/csukuangfj/cppjieba/archive/refs/tags/sherpa-onnx-2024-04-19.tar.gz','03e5264687f0efaef05487a07d49c3f4c0f743347bfbf825df4b30cc75ac5288'),('eigen','https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz','8586084f71f9bde545ee7fa6d00288b264a2b7ac3607b974e54d13e7162c1c72')]
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
