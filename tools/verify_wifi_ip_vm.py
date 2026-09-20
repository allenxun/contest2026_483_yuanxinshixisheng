"""Verify hostap adapter tests and native integrated build; no hardware claims."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
SDK=Path('/home/swl/openvela');PROJECT=SDK/'work/velavision-project'
OUT=SDK/'work/velavision-wifi-ip-20260909';OUT.mkdir(exist_ok=True)
p=subprocess.run(['python3',str(PROJECT/'tools/test_supplicant_vm.py')],capture_output=True,text=True)
report=dict(revision='wifi-ip-20260909',hardware_tested=False,handshake_tests=dict(exit_code=p.returncode,output=p.stdout+p.stderr))
print(p.stdout+p.stderr,flush=True)
assert p.returncode==0
test=OUT/'test_wifi_data'
p=subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(PROJECT/'app/k7radio'),str(PROJECT/'tests/wifi/test_wifi_data.c'),'-o',str(test)],capture_output=True,text=True)
assert p.returncode==0,p.stdout+p.stderr
p=subprocess.run([str(test)],capture_output=True,text=True)
report['data_tests']=dict(exit_code=p.returncode,output=p.stdout+p.stderr)
print(p.stdout+p.stderr,flush=True)
assert p.returncode==0

with (OUT/'build.log').open('w') as log:
    p=subprocess.run(['bash',str(PROJECT/'tools/build_wifi_ip.sh'),str(SDK)],stdout=log,stderr=subprocess.STDOUT)
report['build_exit_code']=p.returncode
if not p.returncode:
    build=SDK/'cmake_out/velavision_wifi_ip_20260909'
    config=(build/'.config').read_text()
    assert 'CONFIG_BLUETOOTH_MAX_PAIRED=8\n' in config
    assert 'CONFIG_EXAMPLES_K7RADIO_IP=y\n' in config
    assert 'CONFIG_NETUTILS_DHCPC=y\n' in config
    report['artifacts']={n:dict(bytes=(build/n).stat().st_size,sha256=hashlib.sha256((build/n).read_bytes()).hexdigest()) for n in ('nuttx.bin','nuttx','.config')}
    report['sources']={str(f.relative_to(PROJECT)):hashlib.sha256(f.read_bytes()).hexdigest() for directory in ('app/k7radio','port/tracked/nuttx/wireless/bluetooth') for f in sorted((PROJECT/directory).rglob('*')) if f.is_file()}
    board='board/kickpi_k7/configs/velavision_wifi_ip_local/defconfig';report['sources'][board]=hashlib.sha256((PROJECT/board).read_bytes()).hexdigest()
    with tarfile.open(OUT/'firmware.tar.gz','w:gz') as archive:
        for n in ('nuttx.bin','nuttx','.config','System.map'):archive.add(build/n,arcname=n)
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('WIFI AUTH build exit',p.returncode,flush=True);raise SystemExit(p.returncode)
