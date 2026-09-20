from pathlib import Path
import subprocess,hashlib,zipfile,json
p=Path(__file__).parent.resolve();repo=p/'git-proof';commit='e7248b26a1ed53fa030c5c459f7ea095dfd276ac'
def git(*args):return subprocess.run(['git','-C',str(repo),*args],capture_output=True,check=True,timeout=20).stdout
raw=git('cat-file','commit',commit);actual=hashlib.sha1(b'commit '+str(len(raw)).encode()+b'\0'+raw).hexdigest();assert actual==commit
root=raw.splitlines()[0].split()[1].decode();(p/'commit-object.txt').write_bytes(raw)
entries={}
for e in git('ls-tree','-rz',commit).split(b'\0'):
 if not e:continue
 spec,name=e.split(b'\t');mode,typ,oid=spec.decode().split();entries[name.decode()]={'mode':mode,'type':typ,'oid':oid}
z=zipfile.ZipFile(p/'unaccepted-eigen.zip');prefix=z.namelist()[0];seen={};differences=[];total=0
for e in z.infolist():
 if e.is_dir():continue
 assert e.filename.startswith(prefix);name=e.filename[len(prefix):];b=z.read(e);total+=len(b);assert total<100*1024*1024
 oid=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest();mode=format(e.external_attr>>16,'o');seen[name]={'mode':mode,'type':'blob','oid':oid}
 if entries.get(name)!=seen[name]:differences.append({'path':name,'git':entries.get(name),'zip':seen[name]})
missing=sorted(set(entries)-set(seen));extra=sorted(set(seen)-set(entries))
report={'commit':commit,'commit_object_sha1_verified':actual,'git_root_tree':root,'git_entries':len(entries),'zip_files':len(seen),'uncompressed_bytes':total,'missing':missing,'extra':extra,'differences':differences,'all_paths_modes_blob_ids_equal':not(missing or extra or differences),'zip_archive_digest_still_rejected':True}
(p/'tree-comparison.json').write_text(json.dumps(report,indent=2));(p/'git-tree-manifest.json').write_text(json.dumps(entries,indent=2));print(json.dumps(report,indent=2)[:2500])
