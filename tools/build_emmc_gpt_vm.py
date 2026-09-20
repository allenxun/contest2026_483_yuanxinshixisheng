"""Stage hash-checked project edits, audit SDK, compile and collect evidence.
No board commands or flashing. Credentials are never copied to the VM.
"""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
REV='emmc-gpt-20260910'
OUT=R/'evidence/build'/REV;OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'verification.json').exists():raise RuntimeError('Completed artifact is immutable; use a new revision')
STAGE=R/'private'/REV;STAGE.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
paths=['tools/sync_sdk.py', 'tools/build_emmc_gpt.sh', 'evidence/build/model-arena-20260910/verification.json', 'evidence/build/emmc-readonly-20260910/verification.json', 'board/kickpi_k7/configs/velavision_emmc_gpt_local/defconfig', 'port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c', 'app/k7emmc/CMakeLists.txt', 'app/k7emmc/emmc_init.c', 'app/k7emmc/emmc_init.h', 'app/k7emmc/gpt_readonly.c', 'app/k7emmc/gpt_readonly.h', 'app/k7emmc/k7emmc_main.c', 'app/k7emmc/Kconfig', 'app/k7emmc/Make.defs', 'app/k7emmc/Makefile', 'app/k7emmc/sdhci_command.c', 'app/k7emmc/sdhci_command.h', 'app/k7emmc/sdhci_control.c', 'app/k7emmc/sdhci_control.h', 'app/k7emmc/sdhci_read.c', 'app/k7emmc/sdhci_read.h', 'app/k7emmc/test_emmc_init.c', 'app/k7emmc/test_gpt_readonly.c', 'app/k7emmc/test_sdhci_command.c', 'app/k7emmc/test_sdhci_control.c', 'app/k7emmc/test_sdhci_read.c']
old=json.loads((R/'private/emmc-gpt-original-hashes.json').read_text(encoding='utf-8-sig'))
manifest={p:dict(new=sha(R/p),old=old.get(p)) for p in paths}
(STAGE/'staging.json').write_text(json.dumps(manifest))
remote=r'''
import hashlib,json,subprocess,tarfile
from pathlib import Path
S=Path('/home/swl/openvela/work/emmc-gpt-stage-20260910')
P=Path('/home/swl/openvela/work/velavision-project')
SDK=P.parents[1];O=SDK/'work/velavision-emmc-gpt-20260910';O.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((S/'staging.json').read_text())
for rel,v in m.items():
 p=P/rel
 if p.exists() and sha(p) not in {v['new'],v['old']}:raise RuntimeError('Unknown mirror edit: '+rel)
for rel in m:
 p=P/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((S/rel).read_bytes())
def run(name,cmd):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 (O/(name+'.log')).write_text(p.stdout)
 print(name,p.returncode,flush=True)
 if p.returncode:print(p.stdout[-8000:]);raise SystemExit(p.returncode)
 return dict(exit_code=p.returncode,log=name+'.log')
audit=run('sync-check',['python3',str(P/'tools/sync_sdk.py'),'--sdk',str(SDK),'--check'])
build=run('build',['bash',str(P/'tools/build_emmc_gpt.sh'),str(SDK)])
B=SDK/'cmake_out/velavision_emmc_gpt_20260910'
assert 'CONFIG_EXAMPLES_K7EMMC=y' in (B/'.config').read_text()
report=dict(revision='emmc-gpt-20260910',build_exit_code=0,hardware_tested=False,sync_audit=audit,
 sources={str(p.relative_to(P)):sha(p) for p in sorted((P/'app/k7radio').rglob('*')) if p.is_file()},
 artifacts={n:dict(bytes=(B/n).stat().st_size,sha256=sha(B/n)) for n in ['nuttx.bin','nuttx','.config']})
profile='board/kickpi_k7/configs/velavision_emmc_gpt_local/defconfig'
report['sources'][profile]=sha(P/profile)
for rel in m:
 if rel.startswith(('port/', 'app/', 'board/')):report['sources'][rel]=sha(P/rel)
(O/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
with tarfile.open(O/'result.tar.gz','w:gz') as t:
 for n in ['nuttx.bin','nuttx','.config']:t.add(B/n,arcname='artifacts/emmc-gpt-20260910/'+n)
 for p in O.iterdir():
  if p.suffix in {'.log','.json'}:t.add(p,arcname='evidence/build/emmc-gpt-20260910/'+p.name)
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
host='swl@192.168.152.131';dest='/home/swl/openvela/work/emmc-gpt-stage-20260910'
def call(args):subprocess.run(args,check=True)
call(['ssh.exe',*options,host,'mkdir -p '+dest])
call(['scp.exe',*options,str(archive),host+':'+dest+'/stage.tar.gz'])
call(['ssh.exe',*options,host,'tar -xzf '+dest+'/stage.tar.gz -C '+dest+' && python3 '+dest+'/build.py'])
result=STAGE/'result.tar.gz'
call(['scp.exe',*options,host+':/home/swl/openvela/work/velavision-emmc-gpt-20260910/result.tar.gz',str(result)])
with tarfile.open(result) as t:
 for member in t.getmembers():
  target=(R/member.name).resolve()
  if not target.is_relative_to(R) or not member.isfile():raise RuntimeError('Unexpected result member')
 t.extractall(R,filter='data')
print('Local build evidence: '+str(OUT))
