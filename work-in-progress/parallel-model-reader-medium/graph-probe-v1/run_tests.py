import hashlib,json,os,pathlib,subprocess,time
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
E=R/'evidence';E.mkdir(exist_ok=True)
CC=pathlib.Path(r'D:\software\mingw64\mingw64\bin\gcc.exe');CXX=CC.with_name('g++.exe')
L=P/'work-in-progress/parallel-llama-pool-safety/evidence/run-20260910T063440936377Z/build/llama/ggml/src'
libs=[L/'ggml.a',L/'ggml-cpu.a',L/'ggml-base.a']
env=dict(os.environ);env['PATH']=str(CC.parent)+os.pathsep+env['PATH']
records=[]
def run(args,timeout=15):
 p=subprocess.run([str(x) for x in args],cwd=R,env=env,capture_output=True,text=True,timeout=timeout)
 records.append(dict(command=[str(x) for x in args],timeout_seconds=timeout,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
try:
 run([CC,'--version'])
 flags=['-std=c11','-Wall','-Wextra','-Werror','-pedantic','-O2','-fstack-usage','-Iinput/include']
 for name,defs,source in [('graph_probe',[],'graph_probe.c'),('graph_probe_main',['-DGP_HOST_MAIN'],'graph_probe_main.c'),('graph_probe_test',['-DGP_TESTING'],'graph_probe.c'),('test_graph_probe',['-DGP_TESTING'],'test_graph_probe.c')]:
  run([CC,*flags,*defs,'-c',source,'-o',E/(name+'.o')],30)
 for exe,objs in [('graph_probe',['graph_probe','graph_probe_main']),('test_graph_probe',['graph_probe_test','test_graph_probe'])]:
  run([CXX,*[E/(o+'.o') for o in objs],'-Wl,--start-group',*libs,'-Wl,--end-group','-pthread','-o',E/(exe+'.exe')],30)
 out=run([E/'graph_probe.exe','both'])
 expected=sum((i%17-8)*(i%7+1) for i in range(4096))
 for line in out.splitlines():
  row=dict(x.split('=',1) for x in line.split() if '=' in x)
  if 'threads_configured' in row:
   assert int(row['checksum'])==expected and row['checked']=='4096' and row['result']=='0',row
 for threads in (2,4):
  for case in range(10):run([E/'test_graph_probe.exe',threads,case])
 run([CC.with_name('nm.exe'),'-u',E/'graph_probe.o'])
finally:
 (E/'host-tests.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'hardware_tested':False,'results':records},indent=2),encoding='utf-8')
print('PASS',len(records),'commands; CPU execution IDs not measured')
