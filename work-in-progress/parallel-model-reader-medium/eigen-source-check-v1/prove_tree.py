from pathlib import Path
import json,hashlib,zipfile,subprocess
p=Path(__file__).parent.resolve();entries=json.loads((p/'git-tree-manifest.json').read_text());z=zipfile.ZipFile(p/'unaccepted-eigen.zip');prefix=z.namelist()[0];nodes={};count=0
for e in z.infolist():
 if e.is_dir():continue
 name=e.filename[len(prefix):];b=z.read(e);v=entries[name];assert v['type']=='blob';assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==v['oid']
 if v['mode']=='100755':assert e.external_attr>>16==0o100755
 else:assert v['mode']=='100644' and e.external_attr>>16==0
 parts=name.split('/');cur=nodes
 for n in parts[:-1]:cur=cur.setdefault(n,{})
 assert parts[-1] not in cur;cur[parts[-1]]=(v['mode'],v['oid']);count+=1
assert count==len(entries)
def tree(d):
 rows=[]
 for n,v in d.items():
  mode,oid=('40000',tree(v)) if isinstance(v,dict) else v
  rows.append((n+('/' if mode=='40000' else ''),mode.encode()+b' '+n.encode()+b'\0'+bytes.fromhex(oid)))
 b=b''.join(x[1] for x in sorted(rows,key=lambda x:x[0].encode()));return hashlib.sha1(b'tree '+str(len(b)).encode()+b'\0'+b).hexdigest()
actual=tree(nodes);expected=json.loads((p/'tree-comparison.json').read_text())['git_root_tree'];assert actual==expected
r={'fixed_commit':'e7248b26a1ed53fa030c5c459f7ea095dfd276ac','expected_git_tree':expected,'reconstructed_tree_from_zip_bytes_and_git_modes':actual,'verified_file_count':count,'all_blob_contents_and_paths_match':True,'git_modes_verified_against_zip_executable_bits':True,'regular_file_mode_source':'fixed Git tree; ZIP DOS entries omit POSIX mode','original_ort_archive_sha1_matches':False,'source_tree_verification_passed':True,'git_version':subprocess.run(['git','--version'],capture_output=True,text=True,check=True).stdout.strip()}
(p/'tree-proof.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
