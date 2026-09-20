from pathlib import Path
import subprocess,os,json
p=Path(__file__).parent.resolve();(p/'empty.gitconfig').write_text('');env=dict(os.environ);env['GIT_CONFIG_NOSYSTEM']='1';env['GIT_CONFIG_GLOBAL']=str(p/'empty.gitconfig');env['GIT_TERMINAL_PROMPT']='0';env['GCM_INTERACTIVE']='Never';log=[]
for cmd in [['git','init',str(p/'git-proof')],['git','-C',str(p/'git-proof'),'-c','credential.helper=','fetch','--depth=1','--no-tags','https://gitlab.com/libeigen/eigen.git','e7248b26a1ed53fa030c5c459f7ea095dfd276ac']]:
 try:
  r=subprocess.run(cmd,env=env,cwd=p,capture_output=True,text=True,timeout=45);log.append({'cmd':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr});
  if r.returncode:break
 except subprocess.TimeoutExpired as e:log.append({'cmd':cmd,'timeout':45});break
(p/'git-fetch.json').write_text(json.dumps(log,indent=2));print(json.dumps(log,indent=2))
