"""Run both independent platform models against the actually merged source."""
import json,os,subprocess,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/audio-mic-20260910/merge-tests';E.mkdir(parents=True,exist_ok=True)
compiler=Path('D:/software/mingw64/mingw64/bin/gcc.exe')
env=dict(os.environ,PATH=str(compiler.parent)+os.pathsep+os.environ.get('PATH',''))
reports=[]
for label,source in [('pull','parallel-cxx-unwind-medium/audio-pad-clock-observe-v1/test_platform.c'),
                     ('clkout','parallel-neon-probe-medium/audio-mclkout-review-v1/test_platform.c')]:
    test=E/(label+'.c');test.write_bytes((R/'work-in-progress'/source).read_bytes())
    for opt in ['O0','O2']:
        exe=E/(label+'-'+opt+'.exe')
        commands=[[str(compiler),'-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-pedantic',
                   '-I'+str(R/'app/k7sound'),str(R/'app/k7sound/platform.c'),str(test),'-o',str(exe)],[str(exe)]]
        for stage,command in enumerate(commands):
            p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=env,timeout=60)
            reports.append(dict(command=command,exit_code=p.returncode,output=p.stdout))
            (E/'results.json').write_text(json.dumps(reports,indent=2))
            print(label,opt,stage,p.returncode,p.stdout)
            if p.returncode:raise SystemExit(p.returncode)
(E/'source-hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'app/k7sound/platform.c',R/'app/k7sound/platform.h']},indent=2))
