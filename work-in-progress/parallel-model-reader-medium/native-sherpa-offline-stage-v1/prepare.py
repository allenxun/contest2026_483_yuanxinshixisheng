from pathlib import Path
import hashlib,json,difflib,subprocess
p=Path(__file__).parent;root=p.parents[2];s=root/'work-in-progress/native-voice-sources/sherpa-onnx-26aa2fa93210376a89de3a65a1a4dd320c37f5e9';f=s/'cmake/onnxruntime.cmake';old=f.read_text(encoding='utf-8');new='if(CMAKE_SYSTEM_NAME STREQUAL "NuttX")\n  include("${CMAKE_CURRENT_LIST_DIR}/onnxruntime-nuttx.cmake")\n  return()\nendif()\n\n'+old
helper=(p/'onnxruntime-nuttx.cmake').read_text(encoding='utf-8-sig')
patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/cmake/onnxruntime.cmake',tofile='b/cmake/onnxruntime.cmake'))+''.join(difflib.unified_diff([],helper.splitlines(True),fromfile='/dev/null',tofile='b/cmake/onnxruntime-nuttx.cmake'))
(p/'candidate.patch').write_text(patch,encoding='utf-8');(p/'onnxruntime.cmake').write_text(new,encoding='utf-8')
check=p/'patch-check';(check/'cmake').mkdir(parents=True);(check/'cmake/onnxruntime.cmake').write_text(old,encoding='utf-8')
r=subprocess.run(['git','apply','--check',str(p/'candidate.patch')],cwd=check,capture_output=True,timeout=15);assert r.returncode==0,r.stderr
r=subprocess.run(['git','apply',str(p/'candidate.patch')],cwd=check,capture_output=True,timeout=15);assert r.returncode==0,r.stderr
assert (check/'cmake/onnxruntime.cmake').read_text(encoding='utf-8')==new
assert (check/'cmake/onnxruntime-nuttx.cmake').read_text(encoding='utf-8')==helper
(p/'patch-check.json').write_text(json.dumps({'git_apply_check':0,'git_apply':0,'output_bytes_match':True,'input_sha256':hashlib.sha256(f.read_bytes()).hexdigest()},indent=2))
cache=(p.parent/'native-sherpa-speech-build-map-v1/asr-initial-cache.cmake').read_text(encoding='utf-8-sig')+'\nset(SBPE_BUILD_PYTHON OFF CACHE BOOL "")\nset(SBPE_ENABLE_TESTS OFF CACHE BOOL "")\nset(CMAKE_DISABLE_FIND_PACKAGE_ICU TRUE CACHE BOOL "No unreviewed host ICU")\nset(CMAKE_DISABLE_FIND_PACKAGE_ZLIB TRUE CACHE BOOL "No unreviewed host zlib")\n'
for key,name in [('KALDI_NATIVE_FBANK','kaldi-native-fbank'),('KALDI_DECODER','kaldi-decoder'),('KALDIFST','kaldifst'),('OPENFST','openfst'),('KISSFFT','kissfft'),('SIMPLE-SENTENCEPIECE','ssentencepiece'),('CPPJIEBA','cppjieba'),('EIGEN','eigen')]:
 cache+=f'set(FETCHCONTENT_SOURCE_DIR_{key} "${{K7_SHERPA_DEPS_ROOT}}/{name}" CACHE PATH "Verified independent source")\n'
(p/'asr-initial-cache.cmake').write_text('if(NOT IS_DIRECTORY "${K7_SHERPA_DEPS_ROOT}")\n  message(FATAL_ERROR "Set K7_SHERPA_DEPS_ROOT to extracted sources before loading cache")\nendif()\n'+cache,encoding='utf-8')
print('patch check + apply exact bytes PASS; no CMake configuration performed')
