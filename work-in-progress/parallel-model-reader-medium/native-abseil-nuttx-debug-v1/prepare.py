from pathlib import Path
import json,hashlib,difflib
p=Path(__file__).parent;root=p.parents[2];src=root/'private/native-ort-env-stage/abseil_cpp';names=['absl/debugging/internal/elf_mem_image.h','absl/debugging/internal/elf_mem_image.cc','absl/debugging/internal/vdso_support.h','absl/debugging/internal/vdso_support.cc','absl/debugging/internal/stacktrace_aarch64-inl.inc','absl/debugging/internal/symbolize.h','absl/debugging/symbolize.cc','absl/debugging/symbolize_unimplemented.inc'];inputs={}
for n in names:
 f=src/n;b=f.read_bytes();out=p/'input'/n;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b);inputs[str(f)]={'sha256':hashlib.sha256(b).hexdigest(),'snapshot':str(out.relative_to(p))}
n=names[0];old=(src/n).read_text();new=old.replace('!defined(__VXWORKS__) && !defined(__hexagon__)','!defined(__VXWORKS__) && !defined(__hexagon__) && !defined(__NuttX__)');assert old!=new
(p/'elf_mem_image.h').write_text(new);(p/'candidate.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+n,tofile='b/'+n)))
log=root/'evidence/native-static-deps3-20260911/build.log';inputs[str(log)]={'sha256':hashlib.sha256(log.read_bytes()).hexdigest()};(p/'inputs.json').write_text(json.dumps(inputs,indent=2))
