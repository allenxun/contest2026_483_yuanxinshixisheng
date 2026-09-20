from pathlib import Path
import difflib
p=Path(__file__).parent;old=(p/'input/01-ort-platform.txt').read_text();anchor='onnxruntime_add_static_library(onnxruntime_common ${onnxruntime_common_src})'
assert old.count(anchor)==1
s=old.replace(anchor,anchor+'\nif(CMAKE_SYSTEM_NAME STREQUAL "NuttX")\n  target_compile_definitions(onnxruntime_common PRIVATE ORT_K7_NUTTX=1)\nendif()')
(p/'platform-gate.cmake').write_text(s);(p/'platform-gate.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='a/cmake/onnxruntime_common.cmake',tofile='b/cmake/onnxruntime_common.cmake')))
