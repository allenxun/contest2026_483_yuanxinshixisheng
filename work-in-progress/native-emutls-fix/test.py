import hashlib,json,resource,subprocess,time
from pathlib import Path
r=Path(__file__).resolve().parent;out=r/('host-'+time.strftime('%Y%m%d-%H%M%S'));out.mkdir()
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
results=[]
for tag,flags in [('O0',['-O0']),('O2',['-O2']),('asan',['-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer'])]:
 cmd=['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-pthread','-DK7_TLS_HOST_TEST',*flags,str(r/'emutls.c'),str(r/'test_emutls.c'),'-o',str(out/tag)]
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60);(out/(tag+'-compile.log')).write_bytes(p.stdout)
 result={'tag':tag,'command':cmd,'compile_exit':p.returncode}
 if p.returncode==0:
  p=subprocess.run([str(out/tag)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60);(out/(tag+'-run.log')).write_bytes(p.stdout);result['run_exit']=p.returncode
 results.append(result)
report={'results':results,'sources':{n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in ('emutls.c','test_emutls.c')},'passed':all(x.get('run_exit')==0 for x in results),'board_verified':False}
(out/'result.json').write_text(json.dumps(report,indent=2));(r/'host-result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
