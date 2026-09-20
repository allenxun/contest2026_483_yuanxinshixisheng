from pathlib import Path
import hashlib,json,subprocess,os
here=Path(__file__).resolve().parent;root=here.parents[1];sdk=Path('/home/swl/openvela')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs=json.loads((here/'inputs.json').read_text()); name='app/voicelink/src/tts_assets.hpp'
fixed=here/'tts_assets.fixed.hpp'
for p in (root/name,sdk/'apps/examples/voicelink/src/tts_assets.hpp'):
    assert sha(p)==inputs[name]
for p in (root/name,sdk/'apps/examples/voicelink/src/tts_assets.hpp'):p.write_bytes(fixed.read_bytes())
inputs[name]=sha(fixed)
(here/'inputs-after-fix.json').write_text(json.dumps(inputs,indent=2))
env=os.environ.copy();env['PATH']=str(sdk/'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin')+':'+env['PATH']
build=sdk/'cmake_out/velavision_spoken_tts_20260913'
with (here/'build-fix1.log').open('xb') as log:
    ret=subprocess.run(['cmake','--build',str(build),'-j4'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
record=json.loads((here/'result.json').read_text());record['initial_build_exit_code']=record['build_exit_code'];record['build_exit_code']=ret.returncode;record['inputs']=inputs
if not ret.returncode:record['artifacts']={n:{'bytes':(build/n).stat().st_size,'sha256':sha(build/n)} for n in ('nuttx','nuttx.bin','.config')}
(here/'result-after-fix.json').write_text(json.dumps(record,indent=2))
assert ret.returncode==0
print('Fixed build passed')
