"""Inspect actual target objects/archives; relocatable link is not firmware proof."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=R/'private/native-voice-link-audit2';P.mkdir(exist_ok=True)
O=R/'evidence/native-voice-link-audit2-20260911';O.mkdir(exist_ok=True)
gate=json.loads((R/'evidence/native-ort-common-compile2-20260911/combined-source-gate.json').read_text())
for row in gate['objects']:
 assert hashlib.sha256((R/row['object']).read_bytes()).hexdigest()==row['sha256']
remote=r'''
import hashlib,json,subprocess,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-link-audit2-20260911')
B=Path('/dev/shm/velavision_audio_sound_20260910')
D=Path('/dev/shm/velavision-static-deps4-20260911/build')
compiler=Path('/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-g++')
nm=str(compiler).replace('g++','nm');ld=str(compiler).replace('g++','ld')
assert json.loads((D.parent/'result.json').read_text())['build']['exit_code']==0
# Restore the upstream POSIX time implementation under the NuttX port's explicit flag.
timecmd=json.loads(Path('/dev/shm/velavision-ort-common1-20260911/17.command.json').read_text())
cut=timecmd.index('-c')
time_source=timecmd[cut+1]
time_output=S/'objects/17.o'
command=timecmd[:cut]+['-DPLATFORM_POSIX','-c',time_source,'-o',str(time_output)]
q=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
(S/'env-time-compile.log').write_bytes(q.stdout)
(S/'env-time-command.json').write_text(json.dumps(command))
assert q.returncode==0
archives=sorted(D.rglob('*.a'));objects=sorted((S/'objects').glob('*.o'))
assert len(objects)==21
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=[dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for p in objects+archives]
cmd=[ld,'-r','-o',str(S/'common-deps.o'),*[str(p) for p in objects],
 '--whole-archive',*[str(p) for p in archives],'--no-whole-archive']
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
(S/'relocatable-link.log').write_bytes(p.stdout)
result=dict(command=cmd,exit_code=p.returncode,archive_count=len(archives),object_count=len(objects),
 firmware_linked=False,hardware_tested=False,inputs=manifest)
if p.returncode==0:
 linked=S/'common-deps.o'
 undefined=subprocess.check_output([nm,'-u',str(linked)],text=True)
 (S/'undefined.txt').write_text(undefined)
 sdk=sorted(B.rglob('*.a'))
 libgcc=Path(subprocess.check_output([str(compiler),'-print-libgcc-file-name'],text=True).strip())
 sdk.append(libgcc)
 libm=Path(subprocess.check_output([str(compiler),'-print-file-name=libm.a'],text=True).strip())
 assert libm.is_file()
 sdk.append(libm)
 definitions=set()
 for archive in sdk:
  q=subprocess.run([nm,'-g','--defined-only',str(archive)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
  assert q.returncode==0,(str(archive),q.stderr)
  for line in q.stdout.splitlines():
   parts=line.split()
   if len(parts)>=3 and len(parts[-2])==1:definitions.add(parts[-1])
 strong=[line.split()[-1] for line in undefined.splitlines() if line.split() and line.split()[0]=='U']
 missing=sorted(set(strong)-definitions)
 (S/'missing-strong.txt').write_text('\n'.join(missing)+'\n')
 (S/'missing-demangled.txt').write_text(subprocess.check_output([str(compiler).replace('g++','c++filt')],input='\n'.join(missing),text=True))
 result.update(relocatable_sha256=sha(linked),strong_undefined=len(set(strong)),missing_from_sdk_archives=len(missing),
  sdk_archives=[dict(path=str(x),sha256=sha(x)) for x in sdk],
  limitation='All-object conservative symbol inventory; archive membership is not final link proof or runtime safety.')
(S/'result.json').write_text(json.dumps(result,indent=2))
with tarfile.open(S/'results.tar.gz','w:gz') as tar:
 for file in S.iterdir():
  if file.suffix in ('.json','.log','.txt'):tar.add(file,arcname=file.name)
print(json.dumps({k:v for k,v in result.items() if k not in ('command','inputs','sdk_archives')}),flush=True)
'''
(P/'audit.py').write_text(remote)
with tarfile.open(P/'stage.tar.gz','w:gz') as tar:
 tar.add(P/'audit.py',arcname='audit.py')
 for i,row in enumerate(gate['objects']):tar.add(R/row['object'],arcname='objects/'+str(i)+'.o')
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-link-audit2-20260911'
def call(args):subprocess.run(args,check=True)
call(['ssh.exe',*options,host,'mkdir '+dest])
call(['scp.exe',*options,str(P/'stage.tar.gz'),host+':'+dest+'/stage.tar.gz'])
call(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && python3 audit.py'])
call(['scp.exe',*options,host+':'+dest+'/results.tar.gz',str(P/'results.tar.gz')])
with tarfile.open(P/'results.tar.gz') as tar:
 for item in tar.getmembers():assert item.isfile() and '/' not in item.name and '\\' not in item.name
 tar.extractall(O,filter='data')
