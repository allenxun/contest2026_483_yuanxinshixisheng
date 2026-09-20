import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parent
sdk=Path('/home/swl/openvela');b=sdk/'cmake_out/velavision_audio_pause_20260911'
assert not b.exists()
obj=sdk/'work/native-emutls-fix/runtime.o'
digest=hashlib.sha256(obj.read_bytes()).hexdigest()
assert digest=='953dd51e573cb78daaf7f21f457e7f695585f66c7c5803ec2a109efa03256f17'
cmd=f'source build/envsetup.sh && cmake -S nuttx -B {b} -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_audio_sound_local -DK7VOICE_NATIVE_ORT_ADD=ON -DK7VOICE_NATIVE_ASR_MODEL=ON -DK7VOICE_NATIVE_ASR_MIC=ON -DK7VOICE_ORT_OBJECT={obj} -DK7VOICE_ORT_OBJECT_SHA256={digest} && cmake --build {b} -j4'
with (r/'build.log').open('xb') as f:
    p=subprocess.run(['bash','-c',cmd],cwd=sdk,stdout=f,stderr=subprocess.STDOUT,timeout=1800)
result=dict(exit_code=p.returncode,command=cmd)
if not p.returncode:result['sha256']=hashlib.sha256((b/'nuttx.bin').read_bytes()).hexdigest()
(r/'build-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
