"""Stage hash-checked project edits, audit SDK, compile and collect evidence.
No board commands or flashing. Credentials are never copied to the VM.
"""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
REV='audio-normal-20260910'
OUT=R/'evidence/build'/REV;OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'verification.json').exists():raise RuntimeError('Completed artifact is immutable; use a new revision')
STAGE=R/'private'/REV;STAGE.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
paths=['tools/sync_sdk.py', 'tools/build_audio_normal.sh', 'evidence/build/model-arena-20260910/verification.json', 'evidence/build/emmc-readonly-20260910/verification.json', 'evidence/build/emmc-gpt-20260910/verification.json', 'board/kickpi_k7/configs/velavision_audio_sound_local/defconfig', 'port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c', 'app/k7emmc/block_readonly.inc', 'app/k7emmc/CMakeLists.txt', 'app/k7emmc/emmc_init.c', 'app/k7emmc/emmc_init.h', 'app/k7emmc/gpt_readonly.c', 'app/k7emmc/gpt_readonly.h', 'app/k7emmc/k7emmc_main.c', 'app/k7emmc/Kconfig', 'app/k7emmc/Make.defs', 'app/k7emmc/Makefile', 'app/k7emmc/sdhci_command.c', 'app/k7emmc/sdhci_command.h', 'app/k7emmc/sdhci_control.c', 'app/k7emmc/sdhci_control.h', 'app/k7emmc/sdhci_read.c', 'app/k7emmc/sdhci_read.h', 'app/k7emmc/test_block_readonly.c', 'app/k7emmc/test_emmc_init.c', 'app/k7emmc/test_gpt_readonly.c', 'app/k7emmc/test_sdhci_command.c', 'app/k7emmc/test_sdhci_control.c', 'app/k7emmc/test_sdhci_read.c']
paths.append('evidence/sync/emmc-block-attempt1.json')
paths.append('evidence/sync/audio-sound-attempt1.json')
paths.append('evidence/build/audio-io-20260910/verification.json')
paths.append('evidence/build/audio-sound-20260910/verification.json')
paths.append('evidence/build/audio-fifo-20260910/verification.json')
paths += ['evidence/sync/smp-diag-baseline.json', 'port/new/nuttx/arch/arm64/include/rk3576/chip.h', 'port/new/nuttx/arch/arm64/include/rk3576/irq.h', 'port/new/nuttx/arch/arm64/src/rk3576/Kconfig', 'port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c', 'port/new/nuttx/arch/arm64/include/rk3576/rk3576_cpu_topology.h', 'port/tracked/nuttx/arch/arm64/src/common/arm64_cpustart.c', 'app/k7smp/CMakeLists.txt', 'app/k7smp/k7smp_main.c', 'app/k7smp/Kconfig', 'app/k7smp/Make.defs', 'app/k7smp/Makefile']
paths.append('evidence/build/smp-reset-20260910/verification.json')
paths.append('evidence/build/smp-four-20260910/verification.json')
paths.append('evidence/sync/smp-service-attempt1.json')
paths += [str(p.relative_to(R)).replace('\\','/') for p in sorted((R/'app/k7load').iterdir()) if p.is_file()]
paths += [str(p.relative_to(R)).replace('\\','/') for p in sorted((R/'app/k7cxx').iterdir()) if p.is_file()]
paths += ['board/kickpi_k7/scripts/dramboot.ld', 'board/kickpi_k7/src/kickpi_k7_appinit.c', 'evidence/sync/cxx-unwind-baseline.json']
paths += ['app/k7neon/CMakeLists.txt', 'app/k7neon/k7neon_main.c', 'app/k7neon/Kconfig', 'app/k7neon/Make.defs', 'app/k7neon/Makefile', 'app/k7neon/neon_hold.S', 'app/k7neon/probe.h', 'app/k7agent/CMakeLists.txt', 'app/k7agent/Kconfig', 'app/k7agent/model_reader/model_reader.c', 'app/k7agent/model_reader/model_reader.h', 'app/k7agent/README.md']
paths += [str(p.relative_to(R)).replace('\\','/') for p in sorted((R/'app/k7eh').iterdir()) if p.is_file()]
paths += [str(p.relative_to(R)).replace('\\','/') for p in sorted((R/'app/k7graph').rglob('*')) if p.is_file()]
paths += [str(p.relative_to(R)).replace('\\','/') for p in sorted((R/'app/k7arena').iterdir()) if p.is_file()]
paths += ['port\\tracked\\nuttx\\drivers\\usbhost\\Kconfig', 'port\\tracked\\nuttx\\drivers\\usbhost\\usbhost_storage.c', 'port\\new\\nuttx\\arch\\arm64\\src\\rk3576\\rk3576_usbhost.c', 'app/k7storage/CMakeLists.txt', 'app/k7storage/k7storage_main.c', 'app/k7storage/Kconfig', 'app/k7storage/README.md']
paths.append('evidence/sync/usb-readonly-attempt1.json')
paths += [p.relative_to(R).as_posix() for p in sorted((R/'app/k7audio').iterdir()) if p.is_file()]
paths += [p.relative_to(R).as_posix() for p in sorted((R/'app/k7audiohw').iterdir()) if p.is_file()]
paths += [p.relative_to(R).as_posix() for p in sorted((R/'app/k7sound').rglob('*')) if p.is_file()]
paths=list(dict.fromkeys(p.replace('\\','/') for p in paths))
old=json.loads((R/'private/audio-normal-original-hashes.json').read_text(encoding='utf-8-sig'))
manifest={p:dict(new=sha(R/p),old=old.get(p)) for p in paths}
(STAGE/'staging.json').write_text(json.dumps(manifest))
remote=r'''
import hashlib,json,subprocess,tarfile
from pathlib import Path
S=Path('/home/swl/openvela/work/audio-normal-stage-20260910')
P=Path('/home/swl/openvela/work/velavision-project')
SDK=P.parents[1];O=SDK/'work/velavision-audio-normal-20260910';O.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((S/'staging.json').read_text())
for rel,v in m.items():
 p=P/rel
 if p.exists() and sha(p) not in {v['new'],v['old']}:raise RuntimeError('Unknown mirror edit: '+rel)
for rel in m:
 p=P/rel;p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists() or sha(p)!=m[rel]['new']:p.write_bytes((S/rel).read_bytes())
def run(name,cmd):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 (O/(name+'.log')).write_text(p.stdout)
 print(name,p.returncode,flush=True)
 if p.returncode:print(p.stdout[-8000:]);raise SystemExit(p.returncode)
 return dict(exit_code=p.returncode,log=name+'.log')
audit=run('sync-check',['python3',str(P/'tools/sync_sdk.py'),'--sdk',str(SDK),'--check'])
build=run('build',['bash',str(P/'tools/build_audio_normal.sh'),str(SDK)])
B=Path('/dev/shm/velavision_audio_sound_20260910')
assert all(x in (B/'.config').read_text().splitlines() for x in ['CONFIG_EXAMPLES_K7SOUND=y','CONFIG_EXAMPLES_K7AUDIO=y','CONFIG_USBHOST_MSC=y','CONFIG_USBHOST_MSC_READONLY=y','CONFIG_EXAMPLES_K7STORAGE=y','CONFIG_EXAMPLES_K7ARENA=y','CONFIG_EXAMPLES_K7GRAPH=y','CONFIG_EXAMPLES_K7EH=y','CONFIG_CXX_WCHAR=y','CONFIG_CXX_MINI_LOCALIZATION=y','CONFIG_FS_LARGEFILE=y','CONFIG_EXAMPLES_K7NEON=y','CONFIG_EXAMPLES_K7CXX=y','CONFIG_HAVE_CXX=y','CONFIG_LIBCXX=y','CONFIG_LIBCXXABI=y','CONFIG_CXX_EXCEPTION=y','CONFIG_CXX_RTTI=y','CONFIG_TLS_NELEM=8','CONFIG_TLS_TASK_NELEM=8','CONFIG_EXAMPLES_K7LOAD=y','CONFIG_SMP=y','CONFIG_SMP_NCPUS=8','CONFIG_NCPUS=8','CONFIG_RK3576_SMP_DIAG=y','CONFIG_EXAMPLES_K7SMP=y','CONFIG_BOARDCTL_RESET=y','CONFIG_SMP_DEFAULT_CPUSET=0x1','CONFIG_EXAMPLES_K7RADIO_IP=y','CONFIG_BCH_DEVICE_READONLY=y'])
assert 'CONFIG_FS_FAT=y' not in (B/'.config').read_text().splitlines()
report=dict(revision='audio-normal-20260910',build_exit_code=0,hardware_tested=False,sync_audit=audit,
 sources={str(p.relative_to(P)):sha(p) for p in sorted((P/'app/k7radio').rglob('*')) if p.is_file()},
 artifacts={n:dict(bytes=(B/n).stat().st_size,sha256=sha(B/n)) for n in ['nuttx.bin','nuttx','.config']})
profile='board/kickpi_k7/configs/velavision_audio_sound_local/defconfig'
report['sources'][profile]=sha(P/profile)
for rel in m:
 if rel.startswith(('port/', 'app/', 'board/')):report['sources'][rel]=sha(P/rel)
(O/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
with tarfile.open(O/'result.tar.gz','w:gz') as t:
 for n in ['nuttx.bin','nuttx','.config']:t.add(B/n,arcname='artifacts/audio-normal-20260910/'+n)
 for p in O.iterdir():
  if p.suffix in {'.log','.json'}:t.add(p,arcname='evidence/build/audio-normal-20260910/'+p.name)
print('BUILD_PASS',flush=True)
'''
(STAGE/'build.py').write_text(remote,encoding='utf-8')
archive=STAGE/'stage.tar.gz'
with tarfile.open(archive,'w:gz') as t:
 for p in paths:t.add(R/p,arcname=p)
 for n in ['staging.json','build.py']:t.add(STAGE/n,arcname=n)
 t.add(R/'work-in-progress/wifi-link/test_prov.c',arcname='test_prov.c')
 t.add(R/'tools/test_prov_wifi_bridge.c',arcname='test_prov_wifi_bridge.c')
options=['-i',r'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/audio-normal-stage-20260910'
def call(args):subprocess.run(args,check=True)
call(['ssh.exe',*options,host,'mkdir -p '+dest])
call(['scp.exe',*options,str(archive),host+':'+dest+'/stage.tar.gz'])
call(['ssh.exe',*options,host,'tar -xzf '+dest+'/stage.tar.gz -C '+dest+' && python3 '+dest+'/build.py'])
result=STAGE/'result.tar.gz'
call(['scp.exe',*options,host+':/home/swl/openvela/work/velavision-audio-normal-20260910/result.tar.gz',str(result)])
with tarfile.open(result) as t:
 for member in t.getmembers():
  target=(R/member.name).resolve()
  if not target.is_relative_to(R) or not member.isfile():raise RuntimeError('Unexpected result member')
 t.extractall(R,filter='data')
print('Local build evidence: '+str(OUT))
