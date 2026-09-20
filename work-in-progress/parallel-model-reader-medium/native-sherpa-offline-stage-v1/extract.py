from pathlib import Path,PurePosixPath
import json,hashlib,zipfile,tarfile,stat
p=Path(__file__).parent;base=p.parent;rows=[];manifest={};omitted=[]
spec=[]
for d,result in [('native-sherpa-deps-v1','download-results.json'),('native-sherpa-deps-v1','nested-download-results.json'),('native-sherpa-deps-v2','download-results.json')]:
 for r in json.loads((base/d/result).read_text()):
  assert r['status']=='VERIFIED'
  if d.endswith('v1'):file=base/d/(r['name']+'-'+r['version']+'.tar.gz')
  else:file=base/d/(r['name']+('.zip' if r['url'].endswith('.zip') else '.tar.gz'))
  spec.append((r['name'],file,r['sha256']))
for name,archive,digest in spec:
 assert hashlib.sha256(archive.read_bytes()).hexdigest()==digest
 target=p/'sources'/name;target.mkdir(parents=True,exist_ok=False);seen=set();size=0;count=0;prefix=None
 def put(n,data,mode):
  global size,count,prefix
  path=PurePosixPath(n)
  if path.is_absolute() or '..' in path.parts or '\\' in n or ':' in n:raise ValueError('unsafe path '+n)
  if prefix is None:prefix=path.parts[0]
  assert path.parts[0]==prefix
  rel=Path(*path.parts[1:]);dest=target/rel
  assert rel.parts and dest.resolve().is_relative_to(target.resolve()) and str(rel).lower() not in seen
  seen.add(str(rel).lower());size+=len(data);assert size<200*1024*1024
  dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);count+=1
  manifest[str(dest.relative_to(p))]={'sha256':hashlib.sha256(data).hexdigest(),'mode':oct(mode),'bytes':len(data)}
 if archive.suffix=='.zip':
  with zipfile.ZipFile(archive) as z:
   for m in z.infolist():
    if m.is_dir():continue
    mode=m.external_attr>>16
    if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0,stat.S_IFREG):omitted.append({'archive':name,'path':m.filename,'reason':'link/nonregular'});continue
    assert m.file_size<32*1024*1024;put(m.filename,z.read(m),mode or 0o100644)
 else:
  with tarfile.open(archive) as t:
   for m in t:
    if m.isdir():continue
    if not m.isfile():omitted.append({'archive':name,'path':m.name,'reason':'link/nonregular'});continue
    assert m.size<32*1024*1024;put(m.name,t.extractfile(m).read(),m.mode)
 rows.append({'name':name,'archive':str(archive),'sha256':digest,'source':str(target),'files':count,'bytes':size})
(p/'extraction.json').write_text(json.dumps({'sources':rows,'omitted':omitted},indent=2));(p/'source-manifest.json').write_text(json.dumps(manifest,indent=2));print('sources',len(rows),'files',len(manifest),'omitted',omitted)
