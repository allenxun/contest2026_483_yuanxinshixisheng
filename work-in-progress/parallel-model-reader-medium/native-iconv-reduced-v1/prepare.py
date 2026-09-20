from pathlib import Path
import hashlib,json,difflib
p=Path(__file__).parent;root=p.parents[2];r=root/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d';out=[];inputs={}
for n in ['cmake/CMakeLists.txt','cmake/onnxruntime_providers_cpu.cmake']:
 f=r/n;old=f.read_text(encoding="utf-8");s=old;inputs[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
 if n.endswith('CMakeLists.txt'):
  a='if(NOT WIN32 AND NOT CMAKE_SYSTEM_NAME STREQUAL "Android")\n  find_package(Iconv REQUIRED)'
  z='''option(K7_NUTTX_REDUCED_NO_STRING_NORMALIZER "Scoped reduced CPU probe without StringNormalizer/Iconv" OFF)
if(K7_NUTTX_REDUCED_NO_STRING_NORMALIZER)
  if(NOT CMAKE_SYSTEM_NAME STREQUAL "NuttX" OR NOT onnxruntime_REDUCED_OPS_BUILD)
    message(FATAL_ERROR "Requires NuttX reduced-op build")
  endif()
  find_package(Python COMPONENTS Interpreter REQUIRED)
  execute_process(COMMAND "${Python_EXECUTABLE}" -B
    "${CMAKE_CURRENT_LIST_DIR}/k7_verify_no_string_normalizer.py"
    "${CMAKE_BINARY_DIR}/op_reduction.generated/onnxruntime/core/providers/cpu/cpu_execution_provider.cc"
    RESULT_VARIABLE k7_registration_result)
  if(NOT k7_registration_result EQUAL 0)
    message(FATAL_ERROR "Generated registration is absent or still references StringNormalizer")
  endif()
  set(ICONV_LIB "")
elseif(NOT WIN32 AND NOT CMAKE_SYSTEM_NAME STREQUAL "Android")
  find_package(Iconv REQUIRED)'''
 else:
  a='onnxruntime_add_static_library(onnxruntime_providers ${onnxruntime_providers_src})'
  z='''if(K7_NUTTX_REDUCED_NO_STRING_NORMALIZER)
  list(REMOVE_ITEM onnxruntime_providers_src
    "${ONNXRUNTIME_ROOT}/core/providers/cpu/text/string_normalizer.cc")
endif()
onnxruntime_add_static_library(onnxruntime_providers ${onnxruntime_providers_src})'''
 assert s.count(a)==1;s=s.replace(a,z);out+=difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='a/'+n,tofile='b/'+n)
(p/'candidate.patch').write_text(''.join(out));(p/'inputs.json').write_text(json.dumps(inputs,indent=2))

