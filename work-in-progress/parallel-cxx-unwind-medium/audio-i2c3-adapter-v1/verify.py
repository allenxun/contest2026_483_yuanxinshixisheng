import hashlib
import json
from pathlib import Path
import shutil
import subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
compiler=shutil.which('gcc');commands=[]
def run(cmd):
 p=subprocess.run(cmd,cwd=str(HERE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
 commands.append(dict(command=cmd,exit_code=p.returncode,output=p.stdout));print(p.stdout)
 if p.returncode: raise RuntimeError('host verification failed')
run([compiler,'--version'])
for name,sources in [('adapter',['adapter.c','test_adapter.c']),('registers',['rk3x_registers.c','test_registers.c'])]:
 for opt in ('-O0','-O2'):
  exe=HERE/(name+opt+'.exe')
  run([compiler,'-std=c11','-Wall','-Wextra','-Werror','-pedantic',opt]+sources+['-o',str(exe)])
  run([str(exe)])
paths=[ROOT/'app/k7radio/k7radio_main.c',ROOT/'work-in-progress/parallel-k7-codec/include/codec_txn.h',
 ROOT/'work-in-progress/parallel-k7-codec/CONTRACT.md',ROOT/'work-in-progress/parallel-k7-audio/HARDWARE.md',
 ROOT/'work-in-progress/parallel-k7-audio/sources/kernel-6.1/arch/arm64/boot/dts/rockchip/rk3576.dtsi',
 ROOT/'work-in-progress/parallel-k7-audio/sources/kernel-6.1/arch/arm64/boot/dts/rockchip/rk3576-pinctrl.dtsi',
 ROOT/'evidence/audio-sdk-extra-20260910/inputs.json']
index=json.loads(paths[-1].read_text(encoding='utf-8'))
for item in index['files']:
 p=ROOT/'evidence/audio-sdk-extra-20260910'/item['path']
 assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'];paths.append(p)
def entry(p):
 data=p.read_bytes();return dict(path=str(p),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
snapshot=HERE/'inputs';snapshot.mkdir(exist_ok=True)
for n,p in enumerate(paths): (snapshot/('%02d-'%n+p.name)).write_bytes(p.read_bytes())
(HERE/'run-evidence.json').write_text(json.dumps(dict(commands=commands,inputs=[entry(p) for p in paths],
 mode='host simulation only',hardware_ready=False,device_access=False),indent=2)+'\n',encoding='utf-8')
(HERE/'delivery.json').write_text(json.dumps(dict(files=[entry(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='delivery.json'],hardware_ready=False),indent=2)+'\n',encoding='utf-8')
