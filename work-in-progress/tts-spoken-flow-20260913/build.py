import hashlib,json,os,subprocess
from pathlib import Path
here=Path(__file__).resolve().parent
project=here.parents[1]
sdk=Path('/home/swl/openvela')
build=sdk/'cmake_out/velavision_spoken_tts_20260913'
runtime=here/'tts-with-current-asr.arm64.o'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
expected='02f6777d0770a11616a6e8e9de505eacb6b1f17b53b9fe30ffeb8da832a1d734'
assert sha(runtime)==expected
assert (here/'k7tts_assets_generated.h').exists()
assert not build.exists(), 'Keep previous build evidence immutable'
for name,digest in json.loads((here/'inputs.json').read_text()).items():
    assert sha(project/name)==digest,name
env=os.environ.copy()
env['PATH']=':'.join(str(sdk/p) for p in ['prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin','prebuilts/tools/python/bin','prebuilts/build-tools/linux-x86_64/bin'])+':'+env.get('PATH','')
env['PYTHONPATH']=str(sdk/'prebuilts/tools/python/dist-packages/kconfiglib')+':'+env.get('PYTHONPATH','')
configure=['cmake','-S','nuttx','-B',str(build),'-G','Ninja','-DBOARD_CONFIG=kickpi_k7:velavision_spoken_tts_local','-DK7VOICE_NATIVE_ORT_ADD=ON','-DK7VOICE_NATIVE_ASR_MODEL=ON','-DK7VOICE_NATIVE_ASR_MIC=ON','-DK7VOICE_NATIVE_TTS=ON','-DK7VOICE_ORT_OBJECT='+str(runtime),'-DK7VOICE_ORT_OBJECT_SHA256='+expected,'-DK7VOICE_TTS_ASSET_INCLUDE='+str(here)]
results={'runtime_sha256':expected,'asset_header_sha256':sha(here/'k7tts_assets_generated.h'),'board_tested':False,'inputs':json.loads((here/'inputs.json').read_text())}
for phase,cmd in [('configure',configure),('build',['cmake','--build',str(build),'-j4'])]:
    with (here/(phase+'.log')).open('xb') as log:
        result=subprocess.run(cmd,cwd=sdk,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
    results[phase+'_exit_code']=result.returncode
    (here/'result.json').write_text(json.dumps(results,indent=2))
    if result.returncode: raise RuntimeError(phase+' failed; inspect log')
results['artifacts']={name:{'bytes':(build/name).stat().st_size,'sha256':sha(build/name)} for name in ('nuttx','nuttx.bin','.config')}
(here/'result.json').write_text(json.dumps(results,indent=2))
print('ARM64 firmware linked; final ELF and board checks still required')
