from pathlib import Path
import subprocess,os
p=Path(__file__).parent.resolve();cc='D:/software/mingw64/mingw64/bin/gcc.exe';cxx=cc.replace('gcc.exe','g++.exe');env=dict(os.environ);env['PATH']=str(Path(cc).parent)+os.pathsep+env.get('PATH','')
log=[]
for opt in ['O0','O2']:
 objs=[]
 for n in ['wifi_broker','wifi_dispatch','wifi_scan','scan_collector']:
  obj=n+'-'+opt+'.o';objs.append(obj)
  cmd=[cc,'-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-Iafter/app/k7radio','-c','after/app/k7radio/'+n+'.c','-o',obj]
  r=subprocess.run(cmd,cwd=p,env=env,capture_output=True,text=True,timeout=30);log +=[repr(cmd),r.stdout,r.stderr];(p/'test-output.txt').write_text('\n'.join(log));assert not r.returncode
 for exceptions in ['on','off']:
  exe='test-'+opt+'-'+exceptions+'.exe'
  cmd=[cxx,'-std=c++17','-'+opt,'-Wall','-Wextra','-Werror','-pthread','-Iafter/app/k7radio','-Iafter/app/voicelink/include','-Icandidate','candidate/voice_wifi_adapter.cpp','candidate/test_adapter.cpp',*objs,'-o',exe]
  if exceptions=='off':cmd.append('-fno-exceptions')
  for args in [cmd,[str(p/exe)]]:
   r=subprocess.run(args,cwd=p,env=env,capture_output=True,text=True,timeout=30);log +=[repr(args),r.stdout,r.stderr];(p/'test-output.txt').write_text('\n'.join(log));assert not r.returncode,(r.stdout,r.stderr)
 # Compile current Controller/core/parsers against exactly these frozen headers.
 for n in ['core','parsers']:
  cmd=[cxx,'-std=c++17','-'+opt,'-Wall','-Wextra','-Werror','-Iafter/app/voicelink/include','-c','after/app/voicelink/src/'+n+'.cpp','-o',n+'-'+opt+'.o']
  r=subprocess.run(cmd,cwd=p,env=env,capture_output=True,text=True,timeout=30);log +=[repr(cmd),r.stdout,r.stderr];(p/'test-output.txt').write_text('\n'.join(log));assert not r.returncode,(r.stdout,r.stderr)
print('O0/O2 exceptions on/off adapter tests and frozen core compilation passed')
