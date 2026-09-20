from pathlib import Path
import subprocess,os
p=Path(__file__).resolve().parent;cc='D:/software/mingw64/mingw64/bin/gcc.exe'
env=dict(os.environ);env['PATH']=str(Path(cc).parent)+os.pathsep+env.get('PATH','')
logs=[]
def run(cmd,fail=False):
 r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=15,env=env)
 logs.append('$ '+' '.join(map(str,cmd))+'\n'+r.stdout+r.stderr+'exit='+str(r.returncode)+'\n');(p/'test-output.txt').write_text(''.join(logs))
 if fail:assert r.returncode!=0 and 'unused-variable' in r.stderr
 else:assert r.returncode==0
flags=['-std=c11','-Wall','-Wextra','-Werror','-Wpedantic','-pthread','-I',p]
run([cc,*flags,'-DCONFIG_EXAMPLES_K7RADIO_SHARED','-c',p/'unused-before.c','-o',p/'unused-before.o'],True)
for shared in [False,True]:run([cc,*flags,*(['-DCONFIG_EXAMPLES_K7RADIO_SHARED'] if shared else []),'-c',p/'unused-after.c','-o',p/('unused-after-'+str(shared)+'.o')])
for opt in ['O0','O2']:
 for original in [True,False]:
  exe=p/('review-'+opt+'-'+str(original)+'.exe')
  run([cc,*flags,'-'+opt,*(['-DORIGINAL'] if original else []),p/'test_review.c',*[p/(n+'.c') for n in ['radio_fence','wifi_broker','wifi_dispatch','wifi_scan','scan_collector']],'-o',exe])
  run([exe]);run([exe,'join'])
print('O0/O2 before/after reproductions passed; original compile error intentionally reproduced')

for opt in ['O0','O2']:
 exe=p/('backend-'+opt+'.exe')
 run([cc,*flags,'-'+opt,p/'test_backend.c',*[p/(n+'.c') for n in ['radio_fence','wifi_broker','wifi_dispatch','wifi_scan','scan_collector']],'-o',exe])
 for scenario in [0,1,2,3]:run([exe,str(scenario)])
print('O0/O2 normal backend and failure-held regressions passed')
