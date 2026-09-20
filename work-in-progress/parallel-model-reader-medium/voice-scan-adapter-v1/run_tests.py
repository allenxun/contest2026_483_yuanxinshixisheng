from pathlib import Path
import subprocess, hashlib, json, os
p=Path(__file__).resolve().parent
cc=Path('D:/software/mingw64/mingw64/bin/gcc.exe')
cxx=cc.with_name('g++.exe')
logs=[]
env=dict(os.environ);env["PATH"]=str(cc.parent)+os.pathsep+env.get("PATH","")
def run(args):
 r=subprocess.run([str(x) for x in args],cwd=p,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30,env=env)
 logs.append('$ '+' '.join(map(str,args))+'\n'+r.stdout+'exit='+str(r.returncode)+'\n')
 (p/'test-output.txt').write_text(''.join(logs))
 if r.returncode: raise SystemExit(r.returncode)
for opt in ['O0','O2']:
 objs=[]
 for name in ['wifi_broker','wifi_dispatch','scan_collector','wifi_scan']:
  out=p/(name+'-'+opt+'.o');objs.append(out)
  run([cc,'-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-Wpedantic','-c',p/(name+'.c'),'-o',out])
 exe=p/('test-'+opt+'.exe')
 run([cxx,'-std=c++17','-'+opt,'-Wall','-Wextra','-Werror','-Wpedantic','-I',p,p/'voice_wifi_adapter.cpp',p/'test.cpp',*objs,'-o',exe])
 run([exe])
 for test in ['test_targeted','test_dispatch_current','test_broker']:
  regression=p/(test+'-'+opt+'.exe')
  run([cc,'-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-Wpedantic','-pthread','-I',p,(p/(test+'.c') if test!='test_broker' else p/'input'/(test+'.c')),*objs,'-o',regression])
  run([regression])
print('O0/O2 passed; commands and raw output in test-output.txt')
