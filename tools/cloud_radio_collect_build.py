"""Collect immutable ARM64 outputs after the isolated build completes."""
import json
from cloud_radio_stage_audit import OUT,remote
code='''import pathlib,hashlib,json,subprocess
sdk=pathlib.Path('/home/swl/openvela')
out=sdk/'cmake_out/velavision_cloud_radio_20260914'
ev=sdk/'work/velavision-project/evidence/cloud-radio-build-20260914'
log=(ev/'arm64-build-retry.log').read_text()
assert '[117/117]' in log and 'FAILED:' not in log
config=(out/'.config').read_text()
symbols=subprocess.check_output([str(sdk/'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-nm'),str(out/'nuttx')]).decode()
report={'build_directory':str(out),'build_log_complete':True,'radio_config_enabled':'CONFIG_EXAMPLES_K7CLOUD_RADIO_READINESS=y' in config.splitlines(),'symbols':{s:any(x.endswith(' '+s) for x in symbols.splitlines()) for s in ['k7cloud_main','k7radio_get_link_snapshot']},'board_loaded':False,'emmc_written':False,'files':{n:{'bytes':(out/n).stat().st_size,'sha256':hashlib.sha256((out/n).read_bytes()).hexdigest()} for n in ['.config','nuttx','nuttx.bin']}}
assert report['radio_config_enabled'] and all(report['symbols'].values())
(ev/'arm64-result-final.json').write_text(json.dumps(report,indent=2)+'\\n')
print(json.dumps(report))
'''
data=json.loads(remote(code))
(OUT/'arm64-result-final.json').write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps(data,indent=2))
