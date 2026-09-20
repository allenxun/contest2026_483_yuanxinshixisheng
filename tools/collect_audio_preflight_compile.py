"""Read exact arena TU preprocessing and unresolved symbols from completed SDK build."""
import json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/build/audio-preflight-20260910'
script=r'''
import json,shlex,subprocess,hashlib
from pathlib import Path
B=Path('/dev/shm/velavision_audio_preflight_20260910')
db=json.loads((B/'compile_commands.json').read_text());out=[]
prefix='/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-'
for u in db:
 if not any(u['file'].endswith('/'+n) for n in ['k7audio_main.c','audio_preflight.c']):continue
 args=shlex.split(u['command']);obj=args[args.index('-o')+1];cmd=[];i=0
 while i<len(args):
  a=args[i];i+=1
  if a in ['-o','-MF','-MT','-MQ']:i+=1;continue
  if a in ['-MD','-MMD','-c']:continue
  cmd.append(a)
 p=subprocess.run(cmd+['-dM','-E'],cwd=u['directory'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
 n=subprocess.run([prefix+'nm','-u',obj],cwd=u['directory'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
 out.append(dict(unit=u,source_sha256=hashlib.sha256(Path(u['file']).read_bytes()).hexdigest(),preprocess_exit=p.returncode,macros=p.stdout,stderr=p.stderr,nm_exit=n.returncode,undefined=n.stdout))
print(json.dumps(out))
'''
opts=['-i',r'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
p=subprocess.run(['ssh.exe',*opts,'swl@192.168.152.131','python3 -'],input=script,text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
assert p.returncode==0,p.stderr
rows=json.loads(p.stdout)
with (E/'audio-compile.json').open('x',encoding='utf-8') as f:json.dump(rows,f,indent=2)
assert len(rows)==2
for x in rows:
 assert x['preprocess_exit']==x['nm_exit']==0
 for macro in ['CONFIG_EXAMPLES_K7AUDIO 1','__NuttX__ 1','CONFIG_USBHOST_MSC 1','CONFIG_USBHOST_MSC_READONLY 1']:
  assert '#define '+macro in x['macros']
 assert '#define CONFIG_FS_FAT ' not in x['macros']
 assert 'host-mock' not in x['unit']['command']
print('2 actual target audio preflight units verified, no host mocks')
