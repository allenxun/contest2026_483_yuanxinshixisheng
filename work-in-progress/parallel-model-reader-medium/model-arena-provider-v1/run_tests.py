import pathlib,subprocess,json,os,time
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2];E=R/'evidence'
CC=pathlib.Path(r'D:\software\mingw64\mingw64\bin\gcc.exe');CXX=CC.with_name('g++.exe')
L=P/'work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063440936377Z/build/llama/ggml/src'
libs=[L/x for x in ['ggml.a','ggml-cpu.a','ggml-base.a']]
env=dict(os.environ);env['PATH']=str(CC.parent)+os.pathsep+env['PATH'];records=[]
def run(args,t=15):
 p=subprocess.run([str(x) for x in args],cwd=R,env=env,capture_output=True,text=True,timeout=t)
 records.append({'command':[str(x) for x in args],'timeout_seconds':t,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
try:
 run([CC,'--version'])
 flags=['-std=c11','-Wall','-Wextra','-Werror','-pedantic','-O2','-fstack-usage','-Iinput/include','-Iinput/buft','-I.']
 # Host compile against ACTUAL target constants/prototypes; do not link/run this object.
 run([CC,*flags,'-Iinput','-c','k7_target_provider.c','-o',E/'target-header-shape-only.o'],30)
 for name,source,defs in [('provider','k7_target_provider.c',[]),('diagnostic','k7_arena_diagnostic.c',[]),('entry','k7_arena_provider_main.c',['-DKAP_HOST_MAIN']),('mock','host-mock/mock.c',[]),('test','host-mock/test_provider.c',[])]:
  run([CC,*flags,*defs,'-Ihost-mock','-c',source,'-o',E/(name+'.o')],30)
 run([CXX,'-std=c++17','-Wall','-Wextra','-Werror','-pedantic','-O2','-Iinput/include','-c','input/buft/k7_host_buft.cpp','-o',E/'buft.o'],30)
 for name,entry in [('provider_probe','entry'),('provider_test','test')]:
  run([CXX,*[E/(x+'.o') for x in ['provider','diagnostic','mock','buft',entry]],'-Wl,--start-group',*libs,'-Wl,--end-group','-pthread','-o',E/(name+'.exe')],30)
 run([E/'provider_probe.exe'])
 for mode in range(9):run([E/'provider_test.exe',mode])
finally:(E/'host-tests.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'target_run':False,'ggml':'real fixed host libraries','arena_API':'mock symbols; address macros overridden only in host-mock header','results':records},indent=2),encoding='utf-8')
print('PASS',len(records),'commands; target API shape only compiled on host')
