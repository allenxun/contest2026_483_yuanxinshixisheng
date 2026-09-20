
import concurrent.futures,hashlib,json,shlex,subprocess,time
from pathlib import Path
S=Path(__file__).resolve().parent
O=S/'result';O.mkdir()
manifest=json.loads((S/'inputs.json').read_text())
B=Path('/home/swl/openvela/cmake_out/velavision_'+manifest['runtime']+'_20260910')
dbraw=(B/'compile_commands.json').read_bytes();db=json.loads(dbraw)
for rel,digest in manifest['files'].items():
 assert hashlib.sha256((S/rel).read_bytes()).hexdigest()==digest,rel
templates={}
for lang,suffix in [('cxx','k7cxx_main.cxx'),('c','k7emmc_main.c')]:
 u=next(x for x in db if x['file'].endswith('/'+suffix))
 args=shlex.split(u['command']);base=[];i=0
 while i<len(args):
  a=args[i];i+=1
  if a in ('-o','-MF','-MT','-MQ'):i+=1;continue
  if a in ('-c','-MD','-MMD') or a.startswith('-Dmain=') or a==u['file']:continue
  base.append(a)
 templates[lang]=dict(args=base,directory=u['directory'])
def compile_unit(pair):
 n,rel=pair;lang='c' if rel.endswith('.c') else 'cxx';t=templates[lang]
 inc=['vendor/include','vendor/src','vendor/common','vendor/ggml/include','vendor/ggml/src','vendor/ggml/src/ggml-cpu','include']
 cmd=t['args']+['-DGGML_USE_CPU','-DGGML_POOL_POSIX=1','-DGGML_SCHED_MAX_COPIES=4','-D_GNU_SOURCE','-fdiagnostics-color=never']
 if manifest['vendor_compat']:
  # Retain upstream warnings; app-specific -Werror should not block vendor
  # feature tests using #if UNDEFINED or intentionally unused static helpers.
  cmd+=['-Wno-error=undef','-Wno-error=unused-function']
 cmd+=['-I'+str(S/p) for p in inc]+['-c',str(S/rel),'-o',str(O/(str(n)+'.o'))]
 started=time.monotonic()
 try:
  p=subprocess.run(cmd,cwd=t['directory'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
  code=p.returncode;raw=p.stdout
 except subprocess.TimeoutExpired as e:code=None;raw=e.stdout or b''
 (O/(str(n)+'.log')).write_bytes(raw)
 return dict(source=rel,command=cmd,exit_code=code,seconds=time.monotonic()-started,log=str(n)+'.log')
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 results=list(pool.map(compile_unit,enumerate(manifest['units'])))
report=dict(scope='Object-only ARM64 NuttX compile; no link or board acceptance',
 config_sha256=hashlib.sha256((B/'.config').read_bytes()).hexdigest(),
 compile_db_sha256=hashlib.sha256(dbraw).hexdigest(),results=results,
 passed=all(x['exit_code']==0 for x in results),units=len(results))
(O/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(units=len(results),passed=sum(x['exit_code']==0 for x in results),failed=[x['source'] for x in results if x['exit_code']!=0])))
