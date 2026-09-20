"""Plan/apply deletion of generated objects only in inactive historical K7 builds."""
import argparse,hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
E=R/'evidence/vm-space-cleanup-20260911';E.mkdir(exist_ok=True)
remote=r'''
import hashlib,json,os,stat,sys,time
from pathlib import Path
B=Path('/home/swl/openvela/cmake_out')
O=Path('/home/swl/openvela/work/space-cleanup-20260911');O.mkdir(exist_ok=True)
assert B.resolve()==B and B.is_dir()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def idle():
 for p in Path('/proc').iterdir():
  if not p.name.isdigit() or int(p.name)==os.getpid():continue
  try:
   cwd=(p/'cwd').resolve(strict=True)
   cmd=(p/'cmdline').read_bytes()
  except (OSError,RuntimeError):continue
  assert not (cwd==B or B in cwd.parents),'active process inside old build tree'
  if b'ninja' in cmd or b'cmake' in cmd or b'ccache' in cmd:
   assert str(B).encode() not in cmd,'active build references old tree'
def protected():
 out={}
 for d in sorted(B.iterdir()):
  if d.is_symlink() or not d.is_dir():continue
  if not d.name.startswith(('rk3576_','velavision_')):continue
  for name in ('nuttx','nuttx.bin','nuttx.map','.config','defconfig','CMakeCache.txt','compile_commands.json','build.ninja','.ninja_log'):
   p=d/name
   if p.is_file() and not p.is_symlink():out[str(p)]=dict(bytes=p.stat().st_size,sha256=sha(p))
 return out
idle()
if sys.argv[1]=='plan':
 assert not (O/'plan.json').exists()
 rows=[];totals={};keep=protected()
 for d in sorted(B.iterdir()):
  if d.is_symlink() or not d.is_dir() or not d.name.startswith(('rk3576_','velavision_')):continue
  if not all((d/n).is_file() for n in ('CMakeCache.txt','build.ninja')):continue
  rules=(d/'build.ninja').read_text(errors='replace')
  for parent,dirs,files in os.walk(d,followlinks=False):
   dirs[:]=[n for n in dirs if not (Path(parent)/n).is_symlink()]
   for name in files:
    p=Path(parent)/name
    if p.suffix not in ('.o','.obj') or 'CMakeFiles' not in p.relative_to(d).parts:continue
    st=p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:continue
    assert p.resolve()==p and B in p.parents
    rel=p.relative_to(d).as_posix()
    if rel not in rules:continue
    rows.append(dict(path=str(p),bytes=st.st_size,mtime_ns=st.st_mtime_ns,inode=st.st_ino))
    totals[d.name]=totals.get(d.name,0)+st.st_size
 plan=dict(root=str(B),targets=rows,bytes=sum(x['bytes'] for x in rows),count=len(rows),builds=totals,protected=keep,
  scope='Only regular single-link generated .o/.obj named in old K7 build.ninja under CMakeFiles. Keep all archives, firmware, sources, config, logs, models, and /dev/shm untouched.')
 (O/'plan.json').write_text(json.dumps(plan,indent=2))
 print(json.dumps(dict(count=plan['count'],bytes=plan['bytes'],build_count=len(totals),plan_sha256=sha(O/'plan.json'))))
elif sys.argv[1]=='apply':
 assert sha(O/'plan.json')==sys.argv[2]
 assert not (O/'applied.json').exists()
 plan=json.loads((O/'plan.json').read_text())
 assert protected()==plan['protected'],'protected inputs drifted'
 for x in plan['targets']:
  p=Path(x['path']);s=p.lstat()
  assert p.resolve()==p and B in p.parents and 'CMakeFiles' in p.parts and p.suffix in ('.o','.obj')
  assert stat.S_ISREG(s.st_mode) and s.st_nlink==1
  assert (s.st_size,s.st_mtime_ns,s.st_ino)==(x['bytes'],x['mtime_ns'],x['inode']),str(p)
 idle();before=os.statvfs(B);deleted=0
 with (O/'deleted.jsonl').open('x') as log:
  for x in plan['targets']:
   p=Path(x['path']);s=p.lstat()
   assert p.resolve()==p and (s.st_size,s.st_mtime_ns,s.st_ino)==(x['bytes'],x['mtime_ns'],x['inode'])
   p.unlink();deleted+=1
   log.write(json.dumps(x)+'\n')
  log.flush()
 assert protected()==plan['protected'],'protected files changed'
 after=os.statvfs(B)
 result=dict(deleted=deleted,logical_bytes=plan['bytes'],available_before=before.f_bavail*before.f_frsize,
 available_after=after.f_bavail*after.f_frsize,protected_files_verified=len(plan['protected']),
 note='Old builds will recompile missing intermediate objects if reused; final archives/firmware/config/logs retained. No SDK sources, current /dev/shm builds, model or board changes.')
 (O/'applied.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
else:raise SystemExit('unknown mode')
'''
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['plan','apply']);parser.add_argument('--plan-hash');a=parser.parse_args()
if a.mode=='apply':assert a.plan_hash and len(a.plan_hash)==64 and all(x in '0123456789abcdef' for x in a.plan_hash)
cmd='python3 - '+a.mode+(' '+a.plan_hash if a.mode=='apply' else '')
p=subprocess.run(['ssh.exe',*options,'swl@192.168.152.131',cmd],input=remote,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(E/(a.mode+'.log')).write_text(p.stdout,encoding='utf-8');print(p.stdout,flush=True)
assert p.returncode==0
for name in (['plan.json'] if a.mode=='plan' else ['applied.json','deleted.jsonl']):
 subprocess.run(['scp.exe',*options,'swl@192.168.152.131:/home/swl/openvela/work/space-cleanup-20260911/'+name,str(E/name)],check=True)
