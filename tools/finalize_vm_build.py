"""Run the unified project entry and freeze its actual resulting files."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
SDK=Path('/home/swl/openvela')
PROJECT=SDK/'work/velavision-project'
OUT=SDK/'work/velavision-integration-20260909'
BUILD=SDK/'cmake_out/velavision_integrated_20260909'
command=['bash',str(PROJECT/'tools/build.sh'),str(SDK)]
with (OUT/'unified-entry-build.log').open('w') as log:
    proc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
report=json.loads((OUT/'integrated-build.json').read_text())
report.update(command=command,exit_code=proc.returncode,source_project=str(PROJECT),sdk_sync_script='tools/sync_sdk.py')
if proc.returncode: raise SystemExit(proc.returncode)
report['files']={n:dict(bytes=(BUILD/n).stat().st_size,sha256=hashlib.sha256((BUILD/n).read_bytes()).hexdigest()) for n in ('.config','nuttx','nuttx.bin')}
nm=SDK/'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-nm'
symbols=subprocess.check_output([str(nm),str(BUILD/'nuttx')],text=True)
report['linked_application_symbols']={n:any(line.endswith(' '+n) for line in symbols.splitlines()) for n in ('k7host_main','gimbal_main','k7npu_main','k7radio_main')}
assert all(report['linked_application_symbols'].values())
report['base_binary_comparison']={}
for name in ('rk3576_usb_photo_direction','rk3576_npu_raw_vendor','rk3576_radio_id36'):
    p=SDK/'cmake_out'/name/'nuttx.bin'
    report['base_binary_comparison'][name]=hashlib.sha256(p.read_bytes()).hexdigest()
(OUT/'integrated-build.json').write_text(json.dumps(report,indent=2)+'\n')
with tarfile.open(OUT/'final-integrated-result.tar.gz','w:gz') as t:
    for n in ('.config','nuttx','nuttx.bin','System.map'):t.add(BUILD/n,arcname='artifacts/integrated-20260909/'+n,recursive=False)
    for n in ('integrated-build.json','unified-entry-build.log'):t.add(OUT/n,arcname='evidence/build/'+n,recursive=False)
print(json.dumps(report))
