from pathlib import Path,PurePosixPath
import tarfile,json,hashlib
p=Path(__file__).parent;prev=p.parent/'native-sherpa-offline-stage-v2';rows=json.loads((prev/'download-results.json').read_text());manifest={};results=[];omitted=[]
for r in rows:
 assert r['status']=='VERIFIED';a=prev/(r['name']+'.tar.gz');assert hashlib.sha256(a.read_bytes()).hexdigest()==r['expected_sha256']
 dest=p/'sources'/r['name'];dest.mkdir(parents=True,exist_ok=False);seen=set();total=0;prefix=None;count=0
 with tarfile.open(a) as tar:
  for m in tar:
   if m.isdir():continue
   if not m.isfile():omitted.append({'archive':r['name'],'path':m.name,'reason':'link/nonregular'});continue
   q=PurePosixPath(m.name);assert not q.is_absolute() and '..' not in q.parts and '\\' not in m.name and ':' not in m.name
   if prefix is None:prefix=q.parts[0]
   assert q.parts[0]==prefix
   rel=Path(*q.parts[1:]);f=dest/rel;assert rel.parts and str(rel).lower() not in seen and f.resolve().is_relative_to(dest.resolve());seen.add(str(rel).lower())
   total+=m.size;assert m.size<32*1024*1024 and total<200*1024*1024
   b=tar.extractfile(m).read();f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b);count+=1
   manifest[str(f.relative_to(p))]={'sha256':hashlib.sha256(b).hexdigest(),'mode':oct(m.mode),'bytes':len(b)}
 results.append({'archive':str(a),'sha256':r['sha256'],'source':str(dest),'files':count,'bytes':total})
(p/'source-manifest.json').write_text(json.dumps(manifest,indent=2));(p/'extraction.json').write_text(json.dumps({'sources':results,'omitted':omitted},indent=2));print('files',len(manifest),'omitted',omitted)
