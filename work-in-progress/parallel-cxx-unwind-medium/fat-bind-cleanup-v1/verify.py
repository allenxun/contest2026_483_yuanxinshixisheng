import hashlib,json,shutil,subprocess
from pathlib import Path
from prepare import prepare,extract,BASE
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
prepare();parts=['#include "mock.h"\n'];extracted=[]
for path,name in [(BASE/'fs_fat32util.c','fat_mount'),(HERE/'candidate/fs_fat32.c','fat_bind'),(HERE/'candidate/fs_fat32.c','fat_unbind')]:
 text=path.read_text(encoding='utf-8');a,b=extract(text,name)
 start=text.rfind('\nstatic int ',0,a) if name!='fat_mount' else text.rfind('\nint ',0,a)
 body=text[start+1:b];parts.append(body)
 extracted.append(dict(name=name,sha256=hashlib.sha256(body.encode()).hexdigest(),path=str(path)))
(HERE/'test.c').write_text('\n'.join(parts)+'\n#include "tests.inc"\n',encoding='utf-8')
commands=[]
def run(cmd):
 p=subprocess.run(cmd,cwd=str(HERE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
 commands.append(dict(command=cmd,exit_code=p.returncode,output=p.stdout));print(p.stdout)
 if p.returncode:
  (HERE/'failed-run.json').write_text(json.dumps(commands,indent=2),encoding='utf-8');raise RuntimeError('failed')
cc=shutil.which('gcc');run([cc,'--version'])
for mode in ('rw','ro'):
 for opt in ('-O0','-O2'):
  exe=HERE/(mode+opt+'.exe')
  flags=['-DCONFIG_FAT_FORCE_READONLY=1'] if mode=='ro' else []
  run([cc,'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-pedantic',opt]+flags+['test.c','-o',str(exe)])
  run([str(exe)])
fixture=HERE/'patch-base/fs/fat';fixture.mkdir(parents=True,exist_ok=True)
(fixture/'fs_fat32.c').write_bytes((BASE/'fs_fat32.c').read_bytes())
run(['git','apply','--check','--unsafe-paths','--directory='+(HERE/'patch-base').as_posix(),str(HERE/'cleanup.patch')])
inputs=[BASE/'fs_fat32.c',BASE/'fs_fat32util.c',BASE.parent.parent/'HANDOFF.md',
 ROOT/'evidence/usb-storage-mount-20260910/nuttx/fs/mount/fs_mount.c',
 ROOT/'evidence/usb-storage-mount-20260910/nuttx/fs/mount/fs_umount2.c']
def entry(p):
 data=p.read_bytes();return dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
for p in inputs[2:]: (HERE/('input-'+p.name)).write_bytes(p.read_bytes())
(HERE/'run-evidence.json').write_text(json.dumps(dict(inputs=[entry(p) for p in inputs],extracted=extracted,commands=commands,
 scope='actual selected FAT functions with mock block/allocator/boot parser; no target execution'),indent=2)+'\n',encoding='utf-8')
(HERE/'delivery.json').write_text(json.dumps(dict(files=[entry(p) for p in sorted(HERE.rglob('*')) if p.is_file() and 'patch-base' not in p.parts and p.name!='delivery.json'],patch_applied=False),indent=2)+'\n',encoding='utf-8')
