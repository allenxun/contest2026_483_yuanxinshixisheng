from pathlib import Path
import subprocess,os
p=Path(__file__).resolve().parent;cc='D:/software/mingw64/mingw64/bin/gcc.exe'
env=dict(os.environ);env['PATH']=str(Path(cc).parent)+os.pathsep+env.get('PATH','');logs=[]
for opt in ['O0','O2']:
 exe=p/('stop-'+opt+'.exe')
 commands=[[cc,'-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-Wpedantic','-pthread','-I',str(p),str(p/'test_stop.c'),*[str(p/(n+'.c')) for n in ['radio_fence','wifi_broker','wifi_dispatch','wifi_scan','scan_collector']],'-o',str(exe)],[str(exe),'scan'],[str(exe),'connect']]
 for cmd in commands:
  r=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=15)
  logs.append('$ '+' '.join(cmd)+'\n'+r.stdout+r.stderr+'exit='+str(r.returncode)+'\n');(p/'test-output.txt').write_text(''.join(logs));assert r.returncode==0
print('O0/O2 scan and connect stop-pause owner invariants passed')
