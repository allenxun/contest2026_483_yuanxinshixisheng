"""Build bounded native A-MSDU reception after actual state/decoder tests."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
SDK=Path('/home/swl/openvela');P=SDK/'work/velavision-project';OUT=SDK/'work/velavision-wifi-amsdu-diag-20260909';OUT.mkdir(exist_ok=True)
report=dict(revision='wifi-amsdu-diag-20260909',hardware_tested=False)
p=subprocess.run(['python3',str(P/'tools/test_supplicant_vm.py')],capture_output=True,text=True)
report['handshake_tests']=dict(exit_code=p.returncode,output=p.stdout+p.stderr);assert p.returncode==0,p.stdout+p.stderr
for name in ('wifi_data','amsdu'):
    test=OUT/('test_'+name)
    p=subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(P/'app/k7radio'),str(P/'tests/wifi'/('test_'+name+'.c')),'-o',str(test)],capture_output=True,text=True)
    assert p.returncode==0,p.stdout+p.stderr
    p=subprocess.run([str(test)],capture_output=True,text=True)
    report[name+'_tests']=dict(exit_code=p.returncode,output=p.stdout+p.stderr);print(p.stdout+p.stderr,flush=True);assert p.returncode==0
with (OUT/'build.log').open('w') as log:
    p=subprocess.run(['bash',str(P/'tools/build_wifi_ip_incremental.sh'),str(SDK)],stdout=log,stderr=subprocess.STDOUT)
report['build_exit_code']=p.returncode
if not p.returncode:
    build=SDK/'cmake_out/velavision_wifi_ip_20260909';config=(build/'.config').read_text()
    for key in ('CONFIG_BLUETOOTH_MAX_PAIRED=8','CONFIG_EXAMPLES_K7RADIO_IP=y','CONFIG_NETUTILS_DHCPC=y'):assert key+'\n' in config
    report['artifacts']={n:dict(bytes=(build/n).stat().st_size,sha256=hashlib.sha256((build/n).read_bytes()).hexdigest()) for n in ('nuttx.bin','nuttx','.config')}
    report['sources']={f.relative_to(P).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for d in ('app/k7radio','port/tracked/nuttx/wireless/bluetooth','tests/wifi') for f in sorted((P/d).rglob('*')) if f.is_file()}
    board='board/kickpi_k7/configs/velavision_wifi_ip_local/defconfig';report['sources'][board]=hashlib.sha256((P/board).read_bytes()).hexdigest()
    with tarfile.open(OUT/'firmware.tar.gz','w:gz') as archive:
        for n in ('nuttx.bin','nuttx','.config','System.map'):archive.add(build/n,arcname=n)
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('AMSDU native build exit',p.returncode,flush=True);raise SystemExit(p.returncode)
