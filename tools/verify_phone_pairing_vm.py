"""Build phone-pairing candidate; preserves previous acceptance artifacts."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
SDK=Path('/home/swl/openvela');PROJECT=SDK/'work/velavision-project'
OUT=SDK/'work/velavision-phone-pairing-20260909';OUT.mkdir(exist_ok=True)
subprocess.run(['python3',str(PROJECT/'tools/test_pairing_pool_vm.py')],check=True)
with (OUT/'build.log').open('w') as log:
    proc=subprocess.run(['bash',str(PROJECT/'tools/build_phone_pairing.sh'),str(SDK)],stdout=log,stderr=subprocess.STDOUT)
report=dict(build_exit_code=proc.returncode,hardware_tested=False,revision='phone-pairing-20260909')
report['pool_tests']=json.loads((OUT/'pool-test/results.json').read_text())
if not proc.returncode:
    build=SDK/'cmake_out/velavision_phone_pairing_20260909'
    config=(build/'.config').read_text()
    assert 'CONFIG_BLUETOOTH_MAX_PAIRED=8\n' in config
    assert 'CONFIG_BLUETOOTH_MAX_CONN=1\n' in config
    assert 'CONFIG_BLUETOOTH_RECYCLE_IDLE_KEYS=y\n' in config
    report['artifacts']={n:dict(bytes=(build/n).stat().st_size,sha256=hashlib.sha256((build/n).read_bytes()).hexdigest()) for n in ('nuttx.bin','nuttx','.config')}
    report['sources']={str(f.relative_to(PROJECT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((PROJECT/'app/k7radio').glob('*')) if f.is_file()}
    board='board/kickpi_k7/configs/velavision_integrated_local/defconfig'
    report['sources'][board]=hashlib.sha256((PROJECT/board).read_bytes()).hexdigest()
    for name in ('bt_keys.c','Kconfig'):
        path='port/tracked/nuttx/wireless/bluetooth/'+name
        report['sources'][path]=hashlib.sha256((PROJECT/path).read_bytes()).hexdigest()
    with tarfile.open(OUT/'firmware.tar.gz','w:gz') as archive:
        for n in ('nuttx.bin','nuttx','.config','System.map'):archive.add(build/n,arcname=n)
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report));raise SystemExit(proc.returncode)
