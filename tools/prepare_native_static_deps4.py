"""Freeze and compile the reviewed NuttX Abseil feature correction separately."""
from pathlib import Path
import hashlib
root=Path(__file__).resolve().parents[1]
candidate=root/'work-in-progress/parallel-model-reader-medium/native-abseil-nuttx-debug-v1'
assert hashlib.sha256((candidate/'outputs.json').read_bytes()).hexdigest()=='174a882596fe3cd3e0744b0567cc416d7037c115e3bf28c8fcb67a142951b0ab'
assert hashlib.sha256((candidate/'elf_mem_image.h').read_bytes()).hexdigest()=='8ffed4026070a5ace55f9d30a8953f1d6673a5214e638997201b942438f94345'
source=(root/'tools/build_native_voice_static_deps3.py').read_text().replace('deps3','deps4')
source=source.replace('import json,shlex,subprocess,hashlib,tarfile','import json,shlex,subprocess,hashlib,tarfile,shutil')
needle="entries=json.loads((B/'compile_commands.json').read_text())"
source=source.replace(needle,"""upstream=Path('/dev/shm/velavision-ort-env3-20260911/abseil_cpp')
shutil.copytree(upstream,S/'abseil_cpp')
header=S/'abseil_cpp/absl/debugging/internal/elf_mem_image.h'
assert hashlib.sha256(header.read_bytes()).hexdigest()=='4d70014ace41a403e3e9ef0804c0ebb4a35c2b0ded81c889b195dbd5eb6b381c'
replacement=(S/'elf_mem_image.h').read_bytes()
assert hashlib.sha256(replacement).hexdigest()=='8ffed4026070a5ace55f9d30a8953f1d6673a5214e638997201b942438f94345'
header.write_bytes(replacement)
"""+needle)
source=source.replace("'-DK7_ABSEIL_SOURCE=/dev/shm/velavision-ort-env3-20260911/abseil_cpp'","'-DK7_ABSEIL_SOURCE='+str(S/'abseil_cpp')")
source=source.replace("tar.add(P/'build.py',arcname='build.py')","tar.add(P/'build.py',arcname='build.py')\n tar.add(R/'work-in-progress/parallel-model-reader-medium/native-abseil-nuttx-debug-v1/elf_mem_image.h',arcname='elf_mem_image.h')")
target=root/'tools/build_native_voice_static_deps4.py'
assert not target.exists()
compile(source,str(target),'exec')
target.write_text(source)
