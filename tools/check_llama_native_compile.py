"""Compile fixed llama CPU sources with existing real NuttX ARM64 flags.

Isolated object-only gate: no SDK sync, link, firmware load or model download.
"""
import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime', choices=['neon_file64', 'cxx_locale'], default='neon_file64')
parser.add_argument('--vendor-compat', action='store_true')
args = parser.parse_args()
B = R/'work-in-progress/parallel-llama-b0'
P = R/'work-in-progress/parallel-llama-pool-safety'
V = B/'vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5'
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
S = R/'private'/('llama-native-'+stamp)
E = R/'evidence/llama-native-compile'/stamp
S.mkdir(parents=True); E.mkdir(parents=True)
files = {}
for item in json.loads((B/'source-manifest.json').read_text()):
    p = B/item['path']
    assert hashlib.sha256(p.read_bytes()).hexdigest() == item['sha256'], p
    if p.is_relative_to(V) and p.relative_to(V).parts[0] in {'src','include','ggml','common'}:
        files['vendor/'+p.relative_to(V).as_posix()] = p
files['vendor/LICENSE'] = V/'LICENSE'
for root, rel in [(B,'candidate/ggml-backend-reg.cpp'), (P,'candidate/ggml-cpu.c'), (P,'include/ggml-pool-safe.h')]:
    index = json.loads((root/'delivery.json').read_text())
    item = next(x for x in index['files'] if x['path'].replace('\\','/') == rel)
    assert hashlib.sha256((root/rel).read_bytes()).hexdigest() == item['sha256']
    files[rel] = root/rel
db = json.loads((B/'evidence/run-20260910T061731515740Z/build/compile_commands.json').read_text())
units = []
for unit in db:
    p = Path(unit['file'])
    if p.is_relative_to(V):
        rel = p.relative_to(V).as_posix()
        if rel == 'ggml/src/ggml-cpu/ggml-cpu.c':
            units.append('candidate/ggml-cpu.c')
        else:
            units.append('vendor/'+rel)
    elif p.name == 'ggml-backend-reg.cpp':
        units.append('candidate/ggml-backend-reg.cpp')
assert len(units) >= 30, units
derivations = []
if args.vendor_compat:
    # Namespace the upstream file-local macro; do not undefine NuttX's UNUSED(a).
    for rel,p in list(files.items()):
        if p.suffix not in {'.c','.cpp'}:
            continue
        text = p.read_text(encoding='utf-8')
        if '#define UNUSED GGML_UNUSED' in text:
            dest = S/'derived'/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(re.sub(r'\bUNUSED\b', 'GGML_LOCAL_UNUSED', text),encoding='utf-8',newline='\n')
            derivations.append(dict(path=rel,original_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                    change='Rename file-local UNUSED token to GGML_LOCAL_UNUSED'))
            files[rel] = dest
manifest = {rel: hashlib.sha256(p.read_bytes()).hexdigest() for rel,p in files.items()}
(S/'inputs.json').write_text(json.dumps(dict(files=manifest,units=units,derivations=derivations,
                                            runtime=args.runtime,vendor_compat=args.vendor_compat),indent=2))
remote = r'''
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
'''
(S/'run.py').write_text(remote,encoding='utf-8',newline='\n')
with tarfile.open(S/'source.tar.gz','w:gz') as archive:
    for rel,p in files.items(): archive.add(p,arcname=rel)
    for name in ['inputs.json','run.py']: archive.add(S/name,arcname=name)
opts=['-i',r'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/llama-native-'+stamp
def call(args): subprocess.run(args,check=True,timeout=1000)
call(['ssh.exe',*opts,host,'mkdir '+dest])
call(['scp.exe',*opts,str(S/'source.tar.gz'),host+':'+dest+'/source.tar.gz'])
call(['ssh.exe',*opts,host,'tar -xzf '+dest+'/source.tar.gz -C '+dest+' && python3 '+dest+'/run.py'])
call(['scp.exe',*opts,'-r',host+':'+dest+'/result/.',str(E)])
(E/'inputs.json').write_bytes((S/'inputs.json').read_bytes())
(E/'runner.py').write_bytes((S/'run.py').read_bytes())
print('EVIDENCE',E)
