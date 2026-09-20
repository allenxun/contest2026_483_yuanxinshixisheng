from pathlib import Path
import hashlib,json,difflib
p=Path(__file__).parent;root=p.parents[2]
src=root/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d/onnxruntime/core/common/logging/logging.cc'
hdr=root/'evidence/model-file-vfs-inputs-20260910/nuttx/include/unistd.h'
(p/'input').mkdir();inputs=[]
for f in [src,hdr]:
 b=f.read_bytes();(p/'input'/f.name).write_bytes(b);inputs.append({'source':str(f),'snapshot':'input/'+f.name,'sha256':hashlib.sha256(b).hexdigest()})
s=src.read_text();s=s.replace('#else\n#include <sys/syscall.h>','#elif !defined(ORT_K7_NUTTX)\n#include <sys/syscall.h>',1)
s=s.replace('#elif defined(__MACH__)\n  uint64_t tid64;','#elif defined(ORT_K7_NUTTX)\n  return static_cast<unsigned int>(gettid());\n#elif defined(__MACH__)\n  uint64_t tid64;',1)
s=s.replace('#elif defined(__MACH__) || defined(__wasm__) || defined(_AIX)\n  return static_cast<unsigned int>(getpid());','#elif defined(ORT_K7_NUTTX) || defined(__MACH__) || defined(__wasm__) || defined(_AIX)\n  return static_cast<unsigned int>(getpid());',1)
(p/'logging.cc').write_text(s)
(p/'candidate.patch').write_text(''.join(difflib.unified_diff(src.read_text().splitlines(True),s.splitlines(True),fromfile='a/onnxruntime/core/common/logging/logging.cc',tofile='b/onnxruntime/core/common/logging/logging.cc')))
(p/'inputs.json').write_text(json.dumps(inputs,indent=2))
print((p/'candidate.patch').read_text())
