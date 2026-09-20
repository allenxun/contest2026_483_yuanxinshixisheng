"""Start an isolated ARM64 compile; never access the board."""
import json
from cloud_radio_stage_audit import remote

worker = r'''
import hashlib,json,pathlib,subprocess
sdk=pathlib.Path('/home/swl/openvela')
out=sdk/'cmake_out/velavision_cloud_radio_20260914'
ev=sdk/'work/velavision-project/evidence/cloud-radio-build-20260914'
command='source build/envsetup.sh >/dev/null && prebuilts/tools/cmake/bin/cmake -S nuttx -B cmake_out/velavision_cloud_radio_20260914 -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_cloud_speech_local && prebuilts/tools/cmake/bin/cmake --build cmake_out/velavision_cloud_radio_20260914 -j4'
rc=subprocess.call(['bash','-c',command],cwd=str(sdk))
report={'build_exit_code':rc,'build_directory':str(out),'board_loaded':False,'emmc_written':False}
if rc==0:
 report['files']={name:{'bytes':(out/name).stat().st_size,'sha256':hashlib.sha256((out/name).read_bytes()).hexdigest()} for name in ['.config','nuttx','nuttx.bin']}
 config=(out/'.config').read_text()
 report['radio_config_enabled']='CONFIG_EXAMPLES_K7CLOUD_RADIO_READINESS=y' in config.splitlines()
 nm=sdk/'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-nm'
 symbols=subprocess.check_output([str(nm),str(out/'nuttx')]).decode()
 report['radio_snapshot_linked']=any(line.endswith(' k7radio_get_link_snapshot') for line in symbols.splitlines())
 report['passed']=report['radio_config_enabled'] and report['radio_snapshot_linked']
(ev/'arm64-result.json').write_text(json.dumps(report,indent=2)+'\n')
'''
launcher='''import pathlib,subprocess
ev=pathlib.Path('/home/swl/openvela/work/velavision-project/evidence/cloud-radio-build-20260914')
ev.mkdir(parents=True,exist_ok=True)
with (ev/'arm64-build.log').open('xb') as log:
 p=subprocess.Popen(['/usr/bin/python3.10','-c',%r],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(p.pid)
''' % worker
print(remote(launcher).decode())
