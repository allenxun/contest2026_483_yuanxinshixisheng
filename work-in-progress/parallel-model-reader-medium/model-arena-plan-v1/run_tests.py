import hashlib,json,os,pathlib,subprocess,time
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
V=P/'work-in-progress/parallel-llama-b0/vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5'
L=P/'work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063440936377Z/build/llama/ggml/src'
C=pathlib.Path(r'D:\software\mingw64\mingw64\bin\g++.exe');E=R/'evidence'
env=dict(os.environ);env['PATH']=str(C.parent)+os.pathsep+env['PATH'];records=[]
def run(args,t=15):
 p=subprocess.run([str(x) for x in args],cwd=R,env=env,capture_output=True,text=True,timeout=t)
 records.append({'command':[str(x) for x in args],'timeout_seconds':t,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
try:
 run([C,'--version'])
 run([C,'-std=c++17','-Wall','-Wextra','-Werror','-pedantic','-O2','-I'+str(V/'ggml/include'),'arena_buffer_lease.cpp','test_lease.cpp','-Wl,--start-group',L/'ggml.a',L/'ggml-cpu.a',L/'ggml-base.a','-Wl,--end-group','-pthread','-o',E/'test_lease.exe'],30)
 run([E/'test_lease.exe'])
finally:(E/'host-tests.json').write_text(json.dumps({'arena_provider':'MOCK tiny aligned array, NOT k7_model_alloc','backend':'real frozen ggml borrowed CPU wrapper','results':records},indent=2),encoding='utf-8')
print('PASS',len(records),'commands; no target arena test')
