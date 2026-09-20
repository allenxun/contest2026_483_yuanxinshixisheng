import hashlib,json,os,pathlib,subprocess,time
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2];E=R/'evidence'
C=pathlib.Path(r'D:\software\mingw64\mingw64\bin\g++.exe')
L=P/'work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063440936377Z/build/llama/ggml/src'
libs=[L/x for x in ['ggml.a','ggml-cpu.a','ggml-base.a']]
env=dict(os.environ);env['PATH']=str(C.parent)+os.pathsep+env['PATH'];records=[]
def run(args,t=15):
 p=subprocess.run([str(x) for x in args],cwd=R,env=env,capture_output=True,text=True,timeout=t)
 records.append({'command':[str(x) for x in args],'timeout_seconds':t,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
try:
 run([C,'--version'])
 flags=['-std=c++17','-Wall','-Wextra','-Werror','-pedantic','-O2','-Iinput/include']
 run([C,*flags,'-c','k7_host_buft.cpp','-o',E/'k7_host_buft.o'],30)
 for variant,defs in [('production',[]),('injected',['-DK7_BUFT_TESTING'])]:
  run([C,*flags,*defs,'k7_host_buft.cpp','test_buft.cpp','-Wl,--start-group',*libs,'-Wl,--end-group','-pthread','-o',E/(variant+'.exe')],30)
  run([E/(variant+'.exe')])
 run([C.with_name('nm.exe'),'-g','--defined-only',E/'k7_host_buft.o'])
finally:(E/'host-tests.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'provider':'fake tiny aligned arena; not K7 hardware','ggml':'real frozen b5046 libraries','results':records},indent=2),encoding='utf-8')
print('PASS',len(records),'commands')
