"""Build and verify the RPA pairing correction without hardware access."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
SDK=Path('/home/swl/openvela');PROJECT=SDK/'work/velavision-project'
OUT=SDK/'work/velavision-phone-rpa-20260909';OUT.mkdir(exist_ok=True)
source=(PROJECT/'port/tracked/nuttx/wireless/bluetooth/bt_smp.c').read_text()
start=source.index('static void smp_pairing_addresses(');brace=source.index('{',start)
depth=1;end=brace+1
while depth:
    depth+=(source[end]=='{')-(source[end]=='}');end+=1
helper=source[start:end]
assert source.count('smp_pairing_addresses(conn, &ia, &ra);')==2
core=(PROJECT/'port/tracked/nuttx/wireless/bluetooth/bt_hcicore.c').read_text()
capture='bt_addr_le_copy(&conn->dst_on_air, &evt->peer_addr);'
assert core.index(capture)<core.index('copy_id_addr(conn, &evt->peer_addr);')
test=(PROJECT/'tests/bluetooth/test_pairing_addresses.c').read_text().replace('/* PRODUCTION_ADDRESS_HELPER */',helper)
(OUT/'test_addresses.c').write_text(test)
subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(OUT/'test_addresses.c'),'-o',str(OUT/'test_addresses')],check=True)
p=subprocess.run([str(OUT/'test_addresses')],capture_output=True,text=True)
report=dict(revision='phone-rpa-20260909',hardware_tested=False,address_tests=dict(exit_code=p.returncode,output=p.stdout+p.stderr))
assert p.returncode==0,p.stdout+p.stderr
print(p.stdout,flush=True)
with (OUT/'build.log').open('w') as log:
    p=subprocess.run(['bash',str(PROJECT/'tools/build_phone_rpa.sh'),str(SDK)],stdout=log,stderr=subprocess.STDOUT)
report['build_exit_code']=p.returncode
if not p.returncode:
    build=SDK/'cmake_out/velavision_phone_rpa_20260909'
    config=(build/'.config').read_text()
    assert 'CONFIG_BLUETOOTH_MAX_PAIRED=8\n' in config and 'CONFIG_BLUETOOTH_RECYCLE_IDLE_KEYS=y\n' in config
    report['artifacts']={n:dict(bytes=(build/n).stat().st_size,sha256=hashlib.sha256((build/n).read_bytes()).hexdigest()) for n in ('nuttx.bin','nuttx','.config')}
    report['sources']={str(f.relative_to(PROJECT)):hashlib.sha256(f.read_bytes()).hexdigest() for directory in ('app/k7radio','port/tracked/nuttx/wireless/bluetooth') for f in sorted((PROJECT/directory).glob('*')) if f.is_file()}
    board='board/kickpi_k7/configs/velavision_integrated_local/defconfig';report['sources'][board]=hashlib.sha256((PROJECT/board).read_bytes()).hexdigest()
    with tarfile.open(OUT/'firmware.tar.gz','w:gz') as archive:
        for n in ('nuttx.bin','nuttx','.config','System.map'):archive.add(build/n,arcname=n)
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report));raise SystemExit(p.returncode)
