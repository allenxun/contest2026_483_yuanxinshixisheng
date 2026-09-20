from pathlib import Path
import hashlib,json,subprocess,os
here=Path(__file__).resolve().parent;root=here.parents[1];sdk=Path('/home/swl/openvela')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=json.loads((here/'result-after-fix.json').read_text());inputs=record['inputs']
pairs=[]
for name in ('src/core.cpp','src/native_speech_output.hpp','include/voicelink/spoken_ssid.hpp'):
    relative='app/voicelink/'+name;source=here/Path(name).name
    for p in (root/relative,sdk/('apps/examples/voicelink/'+name)):
        if relative in inputs: assert sha(p)==inputs[relative]
        else: assert not p.exists()
        pairs.append((source,p))
    inputs[relative]=sha(source)
for source,target in pairs:target.write_bytes(source.read_bytes())
env=os.environ.copy();env['PATH']=str(sdk/'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin')+':'+env['PATH']
build=sdk/'cmake_out/velavision_spoken_tts_20260913'
with (here/'build-speech.log').open('xb') as log:
    result=subprocess.run(['cmake','--build',str(build),'-j4'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
record['build_exit_code']=result.returncode
if not result.returncode:record['artifacts']={n:{'bytes':(build/n).stat().st_size,'sha256':sha(build/n)} for n in ('nuttx','nuttx.bin','.config')}
(here/'result-speech.json').write_text(json.dumps(record,indent=2))
assert result.returncode==0
print('Spoken SSID firmware link passed')
