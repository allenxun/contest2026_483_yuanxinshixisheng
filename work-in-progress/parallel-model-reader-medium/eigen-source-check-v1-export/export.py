from pathlib import Path
import hashlib,json,subprocess
p=Path(__file__).resolve().parent;old=p.parent/'eigen-source-check-v1'
commit='e7248b26a1ed53fa030c5c459f7ea095dfd276ac';manifest=json.loads((old/'git-tree-manifest.json').read_text())
names=list(manifest)
raw=subprocess.run(['git','-C',str(old/'git-proof'),'cat-file','--batch'],input=('\n'.join(manifest[n]['oid'] for n in names)+'\n').encode(),capture_output=True,check=True,timeout=30).stdout
assert len(raw)<32*1024*1024
src=p/'source';src.mkdir(exist_ok=True);seen={};pos=0
for name in names:
 end=raw.index(b'\n',pos);header=raw[pos:end].decode().split();assert header[0]==manifest[name]['oid'] and header[1]=='blob'
 size=int(header[2]);data=raw[end+1:end+1+size];pos=end+2+size
 assert len(data)==size
 oid=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest();assert oid==manifest[name]['oid']
 target=src/name;assert target.resolve().is_relative_to(src.resolve())
 target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 assert hashlib.sha1(b'blob '+str(target.stat().st_size).encode()+b'\0'+target.read_bytes()).hexdigest()==oid
 seen[name]={'sha256':hashlib.sha256(data).hexdigest(),'git_blob':oid,'git_mode':manifest[name]['mode']}
assert set(seen)==set(manifest) and pos==len(raw)
(p/'source-manifest.json').write_text(json.dumps(seen,indent=2))
report={'source_path':str(src),'commit':commit,'tree':'3142f2e6ec15a2cb94c6d1bb751953cbc5f1c948','regular_files':len(seen),'all_blob_bytes_readback_verified':True,'export':'git cat-file --batch exact blobs, not checkout or git archive','mode_note':'Fixed commit modes retained in manifest; preserve when repacking Windows files. No symlinks.','archive_note':'Initial git archive rejected by blob check (export attributes can change bytes); final export uses raw blobs instead.','original_zip_lock_unchanged':True,'source_manifest_sha256':hashlib.sha256((p/'source-manifest.json').read_bytes()).hexdigest()}
(p/'delivery.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));print('delivery_sha256='+hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())
