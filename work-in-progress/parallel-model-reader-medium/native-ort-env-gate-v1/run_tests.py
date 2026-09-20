from pathlib import Path
import subprocess,os
p=Path(__file__).parent.resolve();cc='D:/software/mingw64/mingw64/bin/gcc.exe';env=dict(os.environ);env['PATH']=str(Path(cc).parent)+os.pathsep+env.get('PATH','')
(p/'sample.bin').write_bytes(b'ABCD');(p/'short.bin').write_bytes(b'ABC');log=[]
for opt in ['O0','O2']:
 exe=str(p/('probe-'+opt+'.exe'));cmd=[cc,'-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-pthread','-DK7ENV_PROBE_MAIN','probe.c','model_reader.c','-o',exe]
 r=subprocess.run(cmd,cwd=p,env=env,capture_output=True,text=True,timeout=30);log +=[repr(cmd),r.stdout,r.stderr];assert r.returncode==0,(r.stdout,r.stderr)
 for name,expected in [('sample.bin',0),('short.bin',1),('absent.bin',1)]:
  cmd=[exe,str(p/name)];r=subprocess.run(cmd,cwd=p,env=env,capture_output=True,text=True,timeout=15);log +=[repr(cmd),r.stdout,r.stderr];assert r.returncode==expected
(p/'test-output.txt').write_text('\n'.join(log));print('\n'.join(log))
