from pathlib import Path
import difflib,json,hashlib,re
p=Path(__file__).parent;root=p.parents[2];ort=root/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d';inputs={};diff=[]
def edit(n,changes):
 f=ort/n;b=f.read_bytes();old=b.decode();s=old
 for a,z in changes:
  assert s.count(a)==1,(n,a,s.count(a));s=s.replace(a,z)
 out=p/'candidate'/n;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(s)
 inputs[str(f)]=hashlib.sha256(b).hexdigest();diff.extend(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='a/'+n,tofile='b/'+n))
edit('cmake/CMakeLists.txt',[('    if(UNIX)\n      target_compile_definitions(${target_name} PRIVATE PLATFORM_POSIX)','    if(UNIX OR CMAKE_SYSTEM_NAME STREQUAL "NuttX")\n      target_compile_definitions(${target_name} PRIVATE PLATFORM_POSIX)'),('    target_compile_definitions(${target_name} PRIVATE EIGEN_USE_THREADS)','    if(CMAKE_SYSTEM_NAME STREQUAL "NuttX")\n      target_compile_definitions(${target_name} PRIVATE ORT_K7_NUTTX)\n    endif()\n    target_compile_definitions(${target_name} PRIVATE EIGEN_USE_THREADS)')])
edit('cmake/external/onnxruntime_external_deps.cmake',[('# xnnpack depends on clog','if(CMAKE_SYSTEM_NAME STREQUAL "NuttX")\n  set(CPUINFO_SUPPORTED FALSE)\n  if(onnxruntime_USE_XNNPACK)\n    message(FATAL_ERROR "NuttX CPU gate does not support XNNPACK/cpuinfo")\n  endif()\nendif()\n\n# xnnpack depends on clog'),('if (CMAKE_SYSTEM_NAME STREQUAL "iOS" OR CMAKE_SYSTEM_NAME STREQUAL "Android" OR CMAKE_SYSTEM_NAME STREQUAL "Emscripten")','if (CMAKE_SYSTEM_NAME STREQUAL "iOS" OR CMAKE_SYSTEM_NAME STREQUAL "Android" OR CMAKE_SYSTEM_NAME STREQUAL "Emscripten" OR CMAKE_SYSTEM_NAME STREQUAL "NuttX")')])
edit('cmake/onnxruntime_mlas.cmake',[('    if(ARM64 AND MLAS_SOURCE_IS_NOT_SET )\n        enable_language(ASM)','    if(ARM64 AND MLAS_SOURCE_IS_NOT_SET )\n        if(CMAKE_SYSTEM_NAME STREQUAL "NuttX" AND NOT CMAKE_ASM_COMPILER)\n            message(FATAL_ERROR "Set real target CMAKE_ASM_COMPILER in NuttX toolchain")\n        endif()\n        enable_language(ASM)')])
(p/'candidate.patch').write_text(''.join(diff))
records=[]
for f in sorted((ort/'cmake/external').glob('*.cmake')):
 s=f.read_text();entries=[]
 for m in re.finditer(r'FetchContent_Declare\s*\(',s,re.I):
  start=m.end();i=start;level=1
  while level and i<len(s):level+=(s[i]=='(')-(s[i]==')');i+=1
  block=s[start:i-1];entries.append({'name':block.split()[0],'line':s[:m.start()].count('\n')+1,'block':block})
 if entries or 'PATCH_COMMAND' in s:
  inputs[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest();records.append({'file':str(f),'declarations':entries,'patch_lines':[{'line':i,'text':line} for i,line in enumerate(s.splitlines(),1) if 'PATCH_COMMAND' in line]})
for f in (ort/'cmake/patches').rglob('*.patch'):inputs[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
(p/'fetchcontent-map.json').write_text(json.dumps(records,indent=2));(p/'inputs.json').write_text(json.dumps(inputs,indent=2))
print([(x['name']) for r in records for x in r['declarations']])
