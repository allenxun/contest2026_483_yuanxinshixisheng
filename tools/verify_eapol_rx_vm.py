"""Build/test EAPOL RX changes in the VM; never boots or flashes a board."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
SDK=Path('/home/swl/openvela')
PROJECT=SDK/'work/velavision-project'
OUT=SDK/'work/velavision-eapol-rx-20260909'
OUT.mkdir(exist_ok=True)
report={'hardware_tested':False,'wpa_completed':False,'ip_acquired':False,'tests':[]}
for name in ('codec','queue'):
    exe=OUT/('test_eapol_'+name)
    cmd=['gcc','-std=c11','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
         '-fno-omit-frame-pointer','-I'+str(PROJECT/'app/k7radio'),
         str(PROJECT/f'tests/wifi/test_eapol_{name}.c'),'-o',str(exe)]
    subprocess.run(cmd,check=True)
    p=subprocess.run([str(exe)],capture_output=True,text=True)
    report['tests'].append({'name':name,'command':cmd,'exit_code':p.returncode,'output':p.stdout+p.stderr})
    if p.returncode:
        (OUT/'verification.json').write_text(json.dumps(report,indent=2))
        raise SystemExit(p.returncode)
cmd=['bash',str(PROJECT/'tools/build.sh'),str(SDK)]
with (OUT/'build.log').open('w') as log:
    p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
report['build_exit_code']=p.returncode
if not p.returncode:
    build=SDK/'cmake_out/velavision_integrated_20260909'
    report['artifacts']={n:{'bytes':(build/n).stat().st_size,
       'sha256':hashlib.sha256((build/n).read_bytes()).hexdigest()} for n in ('nuttx.bin','nuttx','.config')}
    report['sources']={str(f.relative_to(PROJECT)):hashlib.sha256(f.read_bytes()).hexdigest()
       for f in sorted((PROJECT/'app/k7radio').glob('*')) if f.is_file()}
    with tarfile.open(OUT/'firmware.tar.gz','w:gz') as t:
        for n in ('nuttx.bin','nuttx','.config','System.map'):t.add(build/n,arcname=n)
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
raise SystemExit(p.returncode)
