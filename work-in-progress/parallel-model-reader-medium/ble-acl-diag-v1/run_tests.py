from pathlib import Path
import subprocess
p=Path(__file__).parent
cc='D:/software/mingw64/mingw64/bin/gcc.exe'
log=[]
for opt in ['O0','O2']:
 for name,src in [('rx',['test.c','candidate/skw_bt.c','candidate/skw_packet.c']),('tx',['test_tx.c'])]:
  cmd=[cc,'-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-pthread','-Istubs','-Icandidate',*src,'-o',name+'-'+opt+'.exe']
  r=subprocess.run(cmd,cwd=p,capture_output=True,text=True,timeout=30);log+=['COMMAND '+repr(cmd),r.stdout,r.stderr];assert r.returncode==0,log
  r=subprocess.run([str(p/(name+'-'+opt+'.exe'))],cwd=p,capture_output=True,text=True,timeout=15);log +=[r.stdout,r.stderr];assert r.returncode==0,log
(p/'test-output.txt').write_text('\n'.join(log));print('\n'.join(log))
