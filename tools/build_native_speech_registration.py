"""Build a new provider archive by recompiling changed registration units only.

The existing ASR archives stay immutable. Reuse is allowed only when the shared
type-control header is byte-identical and every changed built source belongs to
the provider archive with a unique member name.
"""
import subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R/'private/native-speech-registration';P.mkdir(exist_ok=True)
O=R/'evidence/native-speech-registration1-20260911';O.mkdir(exist_ok=True)
remote=r'''
import hashlib,json,os,shlex,shutil,subprocess,tarfile
from pathlib import Path
T=Path('/dev/shm/velavision-ort-session-20260911')
A=Path('/home/swl/openvela/work/native-ort-asr-20260911');B=A/'build'
S=Path('/home/swl/openvela/work/native-speech-registration-20260911');O=S/'result';O.mkdir()
assert json.loads((A/'compile-attempt1/result.json').read_text())['exit_code']==0
os.environ['PYTHONPATH']=str(T/'sources/flatbuffers/python')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old_archive=B/'libonnxruntime_providers.a';old_hash=sha(old_archive)
cmd=['python3',str(T/'ort/tools/ci_build/reduce_op_kernels.py'),str(S/'speech-required.config'),'--cmake_build_dir',str(S/'generated-build'),'--is_extended_minimal_build_or_higher']
q=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
(O/'generate.log').write_bytes(q.stdout);assert q.returncode==0,q.stdout[-2000:]
old=B/'op_reduction.generated';new=S/'generated-build/op_reduction.generated'
old_files={p.relative_to(old).as_posix():sha(p) for p in old.rglob('*') if p.is_file()}
new_files={p.relative_to(new).as_posix():sha(p) for p in new.rglob('*') if p.is_file()}
assert set(old_files)==set(new_files),'Generated file membership changed'
changed={n for n in old_files if old_files[n]!=new_files[n]}
assert changed and all(n.endswith('.cc') for n in changed),'Non-source control changed; full rebuild required'
commands=json.loads((B/'compile_commands.json').read_text());selected=[]
for r in commands:
 f=Path(r['file'])
 try:rel=f.relative_to(old).as_posix()
 except ValueError:continue
 if rel in changed:selected.append((r,rel))
assert selected,'No changed source was in the actual build'
compiler=Path('/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-g++')
ar=str(compiler.with_name('aarch64-none-elf-ar'))
members=subprocess.check_output([ar,'t',str(old_archive)],text=True).splitlines()
objects=[];records=[]
for r,rel in selected:
 args=shlex.split(r['command']);out=Path(args[args.index('-o')+1])
 assert 'onnxruntime_providers.dir' in str(out) and members.count(out.name)==1
 obj=O/out.name;assert not obj.exists()
 args[args.index('-o')+1]=str(obj);args[args.index('-c')+1]=str(new/rel)
 q=subprocess.run(args,cwd=r['directory'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
 (O/(out.name+'.log')).write_bytes(q.stdout)
 assert q.returncode==0,q.stdout[-2000:]
 objects.append(obj);records.append(dict(source=rel,command=args,sha256=sha(obj),exit_code=q.returncode))
target=O/'libonnxruntime_providers.a';shutil.copyfile(old_archive,target)
q=subprocess.run([ar,'rcs',str(target),*[str(p) for p in objects]],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
(O/'archive.log').write_bytes(q.stdout);assert q.returncode==0
assert sha(old_archive)==old_hash,'Old ASR archive changed'
assert subprocess.check_output([ar,'t',str(target)],text=True).splitlines()==members
(O/'result.json').write_text(json.dumps(dict(exit_code=0,base_archive=str(old_archive),base_sha256=old_hash,provider_sha256=sha(target),old_generated=old_files,new_generated=new_files,changed_sources=sorted(changed),compiled_sources=records,
 config_sha256=sha(S/'speech-required.config'),type_control_unchanged=True,model_run=False),indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as t:
 for p in O.iterdir():
  if p.suffix in ('.json','.log'):t.add(p,arcname=p.name)
print('SPEECH_REGISTRATION_PASS',len(records),sha(target),flush=True)
'''
(P/'build.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/native-speech-registration-20260911'
subprocess.run(['ssh.exe',*options,host,'mkdir '+dest],check=True)
for p,n in [(P/'build.py','build.py'),(R/'evidence/native-speech-ort-conversion1-20260911/speech-required.config','speech-required.config')]:
 subprocess.run(['scp.exe',*options,str(p),host+':'+dest+'/'+n],check=True)
subprocess.run(['ssh.exe',*options,host,'python3 '+dest+'/build.py'],check=True)
subprocess.run(['scp.exe',*options,host+':'+dest+'/result/results.tar.gz',str(P/'results.tar.gz')],check=True)
with tarfile.open(P/'results.tar.gz') as t:
 for p in t.getmembers():assert p.isfile() and '/' not in p.name and '\\' not in p.name
 t.extractall(O,filter='data')
