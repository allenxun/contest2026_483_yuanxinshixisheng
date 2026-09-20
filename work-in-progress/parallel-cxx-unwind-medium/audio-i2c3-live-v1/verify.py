from pathlib import Path
import subprocess,json,hashlib
p=Path(__file__).resolve().parent
r=p.parents[2]
sources=['evidence/audio-sdk-extra-20260910/kernel-6.1/drivers/i2c/busses/i2c-rk3x.c',
 'evidence/audio-sdk-extra-20260910/kernel-6.1/drivers/clk/rockchip/clk-rk3576.c',
 'work-in-progress/parallel-cxx-unwind-medium/audio-i2c3-adapter-v1/inputs/04-rk3576.dtsi',
 'work-in-progress/parallel-cxx-unwind-medium/audio-i2c3-clock-v1/i2c3_timing.c',
 'work-in-progress/parallel-cxx-unwind-medium/audio-i2c3-clock-v1/i2c3_timing.h']
a=[]
for i,s in enumerate(sources):
 b=(r/s).read_bytes();n='input-%02d-%s'%(i,Path(s).name)
 (p/n).write_bytes(b);a.append(dict(source=s,snapshot=n,sha256=hashlib.sha256(b).hexdigest()))
(p/'inputs.json').write_text(json.dumps(a,indent=2)+'\n')
results=[]
for opt in ['O0','O2']:
 cmds=[['gcc','-std=c11','-Wall','-Wextra','-Werror','-pedantic','-'+opt,
        'live.c','i2c3_timing.c','test_live.c','-o','test-'+opt+'.exe'],
       [str(p/('test-'+opt+'.exe'))]]
 for cmd in cmds:
  x=subprocess.run(cmd,cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  results.append(dict(command=cmd,exit_code=x.returncode,stdout=x.stdout.decode(),stderr=x.stderr.decode()))
  if x.returncode:break
(p/'run-evidence.json').write_text(json.dumps(dict(scope='synthetic host C only',results=results),indent=2)+'\n')
print(json.dumps(results,indent=2))
files=[dict(path=f.name,size=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in sorted(p.iterdir()) if f.is_file() and f.name!='delivery.json']
(p/'delivery.json').write_text(json.dumps(files,indent=2)+'\n')
assert len(results)==4 and all(x['exit_code']==0 for x in results)
print('delivery SHA256 '+hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())
