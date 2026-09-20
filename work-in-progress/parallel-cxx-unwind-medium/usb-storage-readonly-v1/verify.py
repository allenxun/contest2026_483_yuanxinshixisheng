"""Host-only checks and evidence freezing inside this candidate directory."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
commands=[]
def run(command):
    p=subprocess.run(command,cwd=str(HERE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
    commands.append(dict(command=command,exit_code=p.returncode,output=p.stdout))
    print(p.stdout)
    if p.returncode: raise RuntimeError('host check failed')
def entry(p):
    data=p.read_bytes()
    return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
run([sys.executable,'-B',str(HERE/'prepare_patch.py')])
run([sys.executable,'-B',str(HERE/'test_read_gate.py')])
compiler=shutil.which('gcc')
if not compiler: raise RuntimeError('host GCC missing')
run([compiler,'--version'])
run([compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic',str(HERE/'test_checks.c'),'-o',str(HERE/'test_checks.exe')])
run([str(HERE/'test_checks.exe')])
fixture=HERE/'patch-base'
for relative in ['drivers/usbhost/Kconfig','drivers/usbhost/usbhost_storage.c']:
    dest=fixture/relative; dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes((ROOT/'evidence/usb-storage-inputs-20260910/nuttx'/relative).read_bytes())
run(['git','apply','--check','--unsafe-paths','--directory='+fixture.as_posix(),str(HERE/'msc-readonly.patch')])
references=[]
for directory in ['usb-storage-inputs-20260910','usb-storage-vfs-20260910','usb-storage-mount-20260910']:
    index=ROOT/'evidence'/directory/'inputs.json'
    references.append(entry(index))
    for item in json.loads(index.read_text(encoding='utf-8')):
        if item.get('missing'): continue
        p=index.parent/'nuttx'/item['path']
        actual=entry(p)
        actual['matches_captured_hash']=actual['sha256']==item['sha256']
        if not actual['matches_captured_hash']: raise RuntimeError('input hash mismatch')
        references.append(actual)
for relative in ['port/new/nuttx/arch/arm64/src/rk3576/rk3576_usbhost.c',
                 'port/new/nuttx/drivers/usbhost/usbhost_xhci_rk3576.c',
                 'port/new/nuttx/drivers/usbhost/usbhost_xhci_rk3576.h',
                 'app/k7host/k7host_main.c','artifacts/arena-provider-20260910/.config']:
    references.append(entry(ROOT/relative))
(HERE/'run-evidence.json').write_text(json.dumps(dict(commands=commands,inputs=references,
    scope='host policy/helper + patch applicability only',sdk_built=False,hardware_access=False),indent=2)+'\n',encoding='utf-8')
files=[entry(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='delivery.json']
(HERE/'delivery.json').write_text(json.dumps(dict(files=files,tests='20 Python + 20 C synthetic checks; strict C compilation; patch apply --check',
    patch_applied=False,device_tested=False),indent=2)+'\n',encoding='utf-8')
