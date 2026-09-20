from pathlib import Path
import urllib.request,hashlib,json,tarfile,io,re,time
p=Path(__file__).parent
specs=[('kaldi-native-fbank','1.22.1','b292ddd1fa121f28371d11c14dd016c59c54b3f0dbb2bb2cfdc82d562564d0f5'),('kaldi-decoder','0.2.10','a3d602edc1f422acfe663153faf3f0a716305ec1f95b8fcf9d28d301d6827309')]
results=[]
for name,version,digest in specs:
 org='csukuangfj' if name=='kaldi-native-fbank' else 'k2-fsa';url=f'https://github.com/{org}/{name}/archive/refs/tags/v{version}.tar.gz';row={'name':name,'version':version,'url':url,'expected_sha256':digest}
 try:
  start=time.monotonic();chunks=[];size=0
  with urllib.request.urlopen(url,timeout=25) as r:
   while True:
    b=r.read(1024*1024)
    if not b:break
    size+=len(b);assert size<=32*1024*1024 and time.monotonic()-start<90
    chunks.append(b)
  data=b''.join(chunks);actual=hashlib.sha256(data).hexdigest();assert actual==digest,(actual,digest)
  archive=p/f'{name}-{version}.tar.gz';archive.write_bytes(data);entries=[];cmakes=[]
  with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
   for m in tar:
    if not m.isfile():continue
    if m.name.endswith(('CMakeLists.txt','.cmake')):
     assert m.size<2*1024*1024;b=tar.extractfile(m).read();dst=p/'cmake-snapshots'/m.name;assert dst.resolve().is_relative_to(p.resolve());dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b)
     entries.append({'path':m.name,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)})
  row.update({'status':'VERIFIED','bytes':size,'sha256':actual,'cmake_snapshots':entries})
 except Exception as e:row.update({'status':'FAILED','error':repr(e)})
 results.append(row);(p/'download-results.json').write_text(json.dumps(results,indent=2));print(name,row['status'],row.get('error',''))

