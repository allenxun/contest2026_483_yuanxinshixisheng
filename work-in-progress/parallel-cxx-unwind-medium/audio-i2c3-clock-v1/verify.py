import hashlib,json,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
source=ROOT/'evidence/audio-sdk-extra-20260910/kernel-6.1/drivers/i2c/busses/i2c-rk3x.c'
raw=source.read_bytes();text=raw.decode('utf-8')
a=text.index('static int rk3x_i2c_v1_calc_timings(')
b=text.index('\nstatic void rk3x_i2c_adapt_div',a)
function=text[a:b].replace('unsigned long','uint64_t')
(HERE/'upstream-reference.h').write_text('#include "reference-prefix.h"\n'+function,encoding='utf-8')
(HERE/'i2c-rk3x.frozen.c').write_bytes(raw)
commands=[]
def run(cmd):
 p=subprocess.run(cmd,cwd=str(HERE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
 commands.append(dict(command=cmd,exit_code=p.returncode,output=p.stdout));print(p.stdout)
 if p.returncode:raise RuntimeError('host check failed')
cc=shutil.which('gcc');run([cc,'--version'])
for opt in ('-O0','-O2'):
 exe=HERE/('test'+opt+'.exe')
 run([cc,'-std=c11','-Wall','-Wextra','-Werror','-pedantic',opt,'i2c3_timing.c','test_timing.c','-o',str(exe)])
 run([str(exe)])
def entry(p):
 d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
inputs=[source,ROOT/'evidence/audio-sdk-extra-20260910/inputs.json',
 ROOT/'work-in-progress/parallel-cxx-unwind-medium/audio-i2c3-adapter-v1/rk3x_registers.c',
 ROOT/'work-in-progress/parallel-cxx-unwind-medium/audio-i2c3-adapter-v1/HANDOFF.md']
(HERE/'run-evidence.json').write_text(json.dumps(dict(inputs=[entry(p) for p in inputs],commands=commands,
 upstream_transform='Selected v1 function; unsigned long mapped to uint64_t for target LP64 oracle',hardware_clock_read=False),indent=2)+'\n',encoding='utf-8')
(HERE/'delivery.json').write_text(json.dumps(dict(files=[entry(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='delivery.json'],target_tested=False),indent=2)+'\n',encoding='utf-8')
