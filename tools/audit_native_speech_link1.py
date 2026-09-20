"""Demand-link the real Add client against native ORT; not a firmware test."""
import subprocess
import tarfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
P = R / 'private/native-speech-link1'
O = R / 'evidence/native-speech-link1-20260911'
P.mkdir(exist_ok=True)
O.mkdir(exist_ok=True)
remote = r'''
import hashlib,json,subprocess,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-ort-session-20260911')
O=Path('/home/swl/openvela/work/native-vits-lexicon-20260911/link1')
gate=json.loads((S/'compile-attempt6/result.json').read_text())
assert gate['exit_code']==0 and not gate['timeout'],gate
O.mkdir()
compiler=Path('/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-g++')
ld=str(compiler.with_name('aarch64-none-elf-ld'))
nm=str(compiler.with_name('aarch64-none-elf-nm'))
probe=Path('/dev/shm/velavision-native-asr-add-probe-20260911/add_probe.o')
assert probe.is_file()
ASR=Path('/home/swl/openvela/work/native-vits-lexicon-20260911')
assert json.loads((ASR/'compile-attempt1/result.json').read_text())['exit_code']==0
ORT_ASR=Path('/home/swl/openvela/work/native-ort-asr-20260911')
assert json.loads((ORT_ASR/'compile-attempt1/result.json').read_text())['exit_code']==0
archives=sorted((ORT_ASR/'build').rglob('*.a'))+sorted((ASR/'build').rglob('*.a'))
REG=Path('/home/swl/openvela/work/native-speech-registration-20260911/result')
reg=json.loads((REG/'result.json').read_text())
assert reg['exit_code']==0
replacement=REG/'libonnxruntime_providers.a'
assert hashlib.sha256(replacement.read_bytes()).hexdigest()==reg['provider_sha256']
assert sum(x.name=='libonnxruntime_providers.a' for x in archives)==1
archives=[replacement if x.name=='libonnxruntime_providers.a' else x for x in archives]
assert any(x.name=='libonnxruntime_session.a' for x in archives)
archives.append(S/'config-attempt9/libk7_iconv.a')
archives.append(S/'support-attempt1/libk7_locale.a')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in [probe]+archives]
cmd=[ld,'-r','--undefined=SherpaOnnxCreateOnlineRecognizer','--undefined=SherpaOnnxCreateOfflineTts','--strip-debug','-o',str(O/'session.o'),str(probe),'--start-group',*[str(x) for x in archives],'--end-group']
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
(O/'link.log').write_bytes(p.stdout)
result=dict(exit_code=p.returncode,command=cmd,inputs=inputs,firmware_linked=False,model_run=False,asr_ready=False,ort_kernel_set='ASR+VITS registration; inference untested')
if p.returncode==0:
 undefined=subprocess.check_output([nm,'-u',str(O/'session.o')],text=True)
 (O/'undefined.txt').write_text(undefined)
 sdk=sorted(Path('/dev/shm/velavision_audio_sound_20260910').rglob('*.a'))
 for option in ('-print-libgcc-file-name','-print-file-name=libm.a'):
  sdk.append(Path(subprocess.check_output([str(compiler),option],text=True).strip()))
 definitions=set()
 for a in sdk:
  text=subprocess.check_output([nm,'-g','--defined-only',str(a)],text=True,stderr=subprocess.DEVNULL)
  for line in text.splitlines():
   parts=line.split()
   if len(parts)>=3 and len(parts[-2])==1:definitions.add(parts[-1])
 strong={line.split()[-1] for line in undefined.splitlines() if line.split() and line.split()[0]=='U'}
 missing=sorted(strong-definitions)
 (O/'missing.txt').write_text('\n'.join(missing)+'\n')
 demangled=subprocess.check_output([str(compiler.with_name('aarch64-none-elf-c++filt'))],input='\n'.join(missing),text=True)
 (O/'missing-demangled.txt').write_text(demangled)
 result.update(strong_undefined=len(strong),missing_count=len(missing),relocatable_sha256=sha(O/'session.o'),
  sdk_archives=[dict(path=str(x),sha256=sha(x)) for x in sdk],
  limitation='Normal archive extraction from actual C API client. Definition inventory is not final firmware linkage, layout validation or runtime proof.')
(O/'result.json').write_text(json.dumps(result,indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as t:
 for x in O.iterdir():
  if x.suffix in ('.json','.log','.txt'):t.add(x,arcname=x.name)
print(json.dumps({k:v for k,v in result.items() if k not in ('command','inputs','sdk_archives')}),flush=True)
'''
(P/'audit.py').write_text(remote, encoding='utf-8')
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131'
dest='/dev/shm/velavision-ort-session-20260911'
subprocess.run(['scp.exe',*options,str(P/'audit.py'),host+':'+dest+'/audit-real-speech.py'],check=True)
subprocess.run(['ssh.exe',*options,host,'python3 '+dest+'/audit-real-speech.py'],check=True)
subprocess.run(['scp.exe',*options,host+':/home/swl/openvela/work/native-vits-lexicon-20260911/link1/results.tar.gz',str(P/'results.tar.gz')],check=True)
with tarfile.open(P/'results.tar.gz') as t:
 for x in t.getmembers():
  assert x.isfile() and '/' not in x.name and '\\' not in x.name
 t.extractall(O,filter='data')
