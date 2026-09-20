from pathlib import Path
import hashlib
R=Path(__file__).resolve().parents[1]
s=(R/'tools/configure_native_ort_session8.py').read_text().replace('native-ort-session-config8','native-ort-session-config9').replace('config-attempt8','config-attempt9')
file=R/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d/cmake/onnxruntime_providers_cpu.cmake'
digest=hashlib.sha256(file.read_bytes()).hexdigest()
insert=""" # Native CPU-only static runtime does not build the dynamic provider loader library.
 provider=S/'ort/cmake/onnxruntime_providers_cpu.cmake'
 before=provider.read_bytes()
 assert hashlib.sha256(before).hexdigest()=='DIGEST'
 text=before.decode()
 old='AND NOT CMAKE_SYSTEM_NAME STREQUAL "Emscripten")'
 new='AND NOT CMAKE_SYSTEM_NAME STREQUAL "Emscripten"\\n                                  AND NOT CMAKE_SYSTEM_NAME STREQUAL "NuttX")'
 assert text.count(old)==1
 provider.write_text(text.replace(old,new))
 records.append(dict(name='exclude-native-dynamic-provider',before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(provider.read_bytes()).hexdigest()))
""".replace('DIGEST',digest)
needle=" original=Path('/dev/shm/velavision-static-deps4-20260911/toolchain.cmake').read_text()"
assert needle in s;s=s.replace(needle,insert+needle)
target=R/'tools/configure_native_ort_session9.py';assert not target.exists()
compile(s,str(target),'exec');target.write_text(s)
