from pathlib import Path
import subprocess,os
env=dict(os.environ);env["PATH"]="D:/software/mingw64/mingw64/bin"+os.pathsep+env.get("PATH","")
p=Path(__file__).resolve().parent
cc='D:/software/mingw64/mingw64/bin/gcc.exe'
logs=[]
for opt in ['O0','O2']:
 exe=p/('test-'+opt+'.exe')
 for cmd in [[cc,'-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-Wpedantic',str(p/'test_scan.c'),str(p/'radio_fence.c'),'-o',str(exe)],[str(exe)]]:
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=20,env=env)
  logs.append('$ '+' '.join(cmd)+'\n'+r.stdout+r.stderr+'exit='+str(r.returncode)+'\n')
  (p/'test-output.txt').write_text(''.join(logs))
  if r.returncode:raise SystemExit(r.returncode)
print('O0/O2 real scan seam and fence tests passed')

for opt in ['O0','O2']:
 exe=p/('backend-'+opt+'.exe')
 cmd=[cc,'-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-Wpedantic','-pthread','-I',str(p),str(p/'test_backend.c'),*[str(p/(n+'.c')) for n in ['radio_fence','wifi_broker','wifi_dispatch','wifi_scan','scan_collector']],'-o',str(exe)]
 for c in [cmd,[str(exe)],*[ [str(exe),str(i)] for i in [1,2,3]]]:
  r=subprocess.run(c,capture_output=True,text=True,timeout=20,env=env)
  logs.append('$ '+' '.join(c)+'\n'+r.stdout+r.stderr+'exit='+str(r.returncode)+'\n')
  (p/'test-output.txt').write_text(''.join(logs))
  if r.returncode:raise SystemExit(r.returncode)
print('O0/O2 target backend seam passed')

for opt in ['O0','O2']:
 objs=[]
 cmds=[]
 for n in ['wifi_broker','wifi_dispatch','wifi_scan','scan_collector']:
  obj=p/(n+'-'+opt+'.o');objs.append(str(obj));cmds.append([cc,'-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-Wpedantic','-c',str(p/(n+'.c')),'-o',str(obj)])
 exe=p/('adapter-'+opt+'.exe');cmds.append([cc.replace('gcc.exe','g++.exe'),'-std=c++17','-'+opt,'-Wall','-Wextra','-Werror','-Wpedantic','-I',str(p),str(p/'test_adapter.cpp'),str(p/'voice_wifi_adapter.cpp'),*objs,'-o',str(exe)]);cmds.append([str(exe)])
 for cmd in cmds:
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=20,env=env)
  logs.append('$ '+' '.join(cmd)+'\n'+r.stdout+r.stderr+'exit='+str(r.returncode)+'\n');(p/'test-output.txt').write_text(''.join(logs))
  if r.returncode:raise SystemExit(r.returncode)
print('O0/O2 updated adapter tests passed')
