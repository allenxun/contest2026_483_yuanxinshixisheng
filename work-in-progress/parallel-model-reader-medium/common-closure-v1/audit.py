from pathlib import Path
import zipfile,json,hashlib
p=Path(__file__).parent;r=p.parents[1]/'native-voice-sources';ort=r/'onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d';inputs={}
def freeze(f):
 b=f.read_bytes();inputs[str(f)]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)};return b
patterns=['core/common/*.cc','core/common/logging/*.cc','core/common/logging/sinks/*.cc','core/platform/posix/*.cc','core/quantization/*.cc']
files=set()
for pat in patterns:files.update((ort/'onnxruntime').glob(pat))
for n in ['env','env_time','path_lib','telemetry','logging/make_platform_default_log_sink']:files.add(ort/'onnxruntime/core/platform'/ (n+'.cc'))
for f in files:freeze(f)
(p/'common-sources.txt').write_text('\n'.join(str(f) for f in sorted(files))+'\n')
for name in ['cmake/onnxruntime_common.cmake','cmake/CMakeLists.txt','cmake/onnxruntime_config.h.in','cmake/external/abseil-cpp.cmake','cmake/external/onnxruntime_external_deps.cmake','cmake/deps.txt','include/onnxruntime/core/platform/ort_mutex.h','onnxruntime/core/platform/EigenNonBlockingThreadPool.h']: 
 f=ort/name
 if f.exists():freeze(f)
for lib in ['google_nsync','abseil_cpp']:
 zpath=r/'deps'/ (lib+'.zip');freeze(zpath)
 with zipfile.ZipFile(zpath) as z:
  matches=[n for n in z.namelist() if n.endswith('CMakeLists.txt') or (lib=='google_nsync' and ('platform/' in n and n.endswith(('.cc','.h','.c'))))]
  out=[]
  for n in matches:
   b=z.read(n);inputs[str(zpath)+'!'+n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
   out.append('\nFILE '+n+'\n'+''.join(f'{i}: {s}\n' for i,s in enumerate(b.decode(errors='replace').splitlines(),1)))
  (p/(lib+'-source-lines.txt')).write_text(''.join(out))
freeze(p.parent/'env-gate-v2/env-gate.cc')
(p/'inputs.json').write_text(json.dumps(inputs,indent=2));print('common units',len(files))
# Resolve declared Abseil target graph without configuring or executing dependency CMake.
import re
with zipfile.ZipFile(r/'deps/abseil_cpp.zip') as z:
 targets={}
 for n in z.namelist():
  if not n.endswith('CMakeLists.txt'):continue
  s=z.read(n).decode()
  for m in re.finditer(r'absl_cc_library\s*\(',s):
   start=m.end();depth=1;i=start
   while depth and i<len(s):
    depth+=(s[i]=='(')-(s[i]==')');i+=1
   block=s[start:i-1];name=re.search(r'\bNAME\s+(\w+)',block)
   if name:
    targets[name[1]]={'file':n,'line':s[:m.start()].count('\n')+1,'deps':sorted(set(re.findall(r'absl::(\w+)',block))),'block':block}
 roots=re.findall(r'absl::(\w+)',(ort/'cmake/external/abseil-cpp.cmake').read_text())
 closure=set();missing=set()
 def walk(n):
  if n in closure:return
  closure.add(n)
  if n not in targets:missing.add(n);return
  for d in targets[n]['deps']:walk(d)
 roots=[n for n in roots if n!='lts_20240116']
 for n in roots:walk(n)
 report={'roots':sorted(set(roots)),'closure':{n:targets.get(n) for n in sorted(closure)},'missing':sorted(missing),'limitations':'Static declared graph includes conditionally compiled source entries; not configured target archive list or proven NuttX link.'}
 (p/'abseil-declared-closure.json').write_text(json.dumps(report,indent=2));print('abseil declared closure',len(closure),'missing',missing)

