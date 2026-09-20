"""Prepare isolated MIT libc compile gate; does not change firmware configuration."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root / 'tools/build_native_voice_static_deps.py').read_text()
source = source.replace('native-static-deps2-20260911', 'native-static-deps3-20260911')
source = source.replace('velavision-static-deps2-20260911', 'velavision-static-deps3-20260911')
source = source.replace('native-static-deps-stage', 'native-static-deps3-stage')
source = source.replace("lines += ['set(CMAKE_'", "flags.append('-DCONFIG_ALLOW_MIT_COMPONENTS=1')\n lines += ['set(CMAKE_'")
source = source.replace("results.update(linked=False", "results.update(isolated_compile_config_override='CONFIG_ALLOW_MIT_COMPONENTS=1; real frozen lib_strptime.c compiled alongside; final SDK config unchanged',linked=False")
old = "for name in ('CMakeLists.txt','ort-abseil-targets.cmake'):tar.add(C/name,arcname=name)"
new = """for name in ('ort-abseil-targets.cmake',):tar.add(C/name,arcname=name)
 cmake=(C/'CMakeLists.txt').read_text()+'''\n# Compile actual NuttX implementation, never a declaration-only stub.
add_library(k7_libc_time_gate STATIC lib_strptime.c)
add_dependencies(k7_native_deps k7_libc_time_gate)
'''
 (P/'CMakeLists.txt').write_text(cmake)
 tar.add(P/'CMakeLists.txt',arcname='CMakeLists.txt')
 tar.add(R/'evidence/native-strptime-input-20260911/lib_strptime.c',arcname='lib_strptime.c')"""
assert old in source
source = source.replace(old, new)
target = root / 'tools/build_native_voice_static_deps3.py'
assert not target.exists(), 'Preserve existing build script'
compile(source, str(target), 'exec')
target.write_text(source)
print(target)
