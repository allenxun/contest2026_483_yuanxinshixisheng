"""Apply one exact reviewed header to isolated dependency stage; preserve input."""
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=R/'private/native-kiss-patch';P.mkdir(exist_ok=True)
O=R/'evidence/native-kiss-patch-20260911';O.mkdir(exist_ok=True)
header=R/'work-in-progress/parallel-model-reader-medium/native-kissfft-log-macro-v1/candidate/kiss_fft_log.h'
assert hashlib.sha256(header.read_bytes()).hexdigest()=='c64bd308e46162c63c15e842174de29ba1e9326a95278e3cc77b55d3bc3ce693'
remote=r'''
import hashlib,json
from pathlib import Path
S=Path('/home/swl/openvela/work/native-sherpa-config2-20260911')
O=S/'kiss-patch';O.mkdir()
p=Path('/dev/shm/velavision-sherpa-asr-20260911/sources/kissfft/kiss_fft_log.h')
old=p.read_bytes();new=(S/'kiss_fft_log.candidate.h').read_bytes()
assert hashlib.sha256(old).hexdigest()=='f954cb6890ec999f7fbc80cdd1c8c0194bbaeb0f1c27e11bd23450f53871cf8c'
assert hashlib.sha256(new).hexdigest()=='c64bd308e46162c63c15e842174de29ba1e9326a95278e3cc77b55d3bc3ce693'
(O/'before.h').write_bytes(old);p.write_bytes(new);(O/'after.h').write_bytes(new)
(O/'result.json').write_text(json.dumps(dict(path=str(p),before=hashlib.sha256(old).hexdigest(),after=hashlib.sha256(p.read_bytes()).hexdigest(),scope='isolated staged dependency only'),indent=2))
print('PATCHED_EXACT_HEADER')
'''
(P/'apply.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/native-sherpa-config2-20260911'
for p,n in [(P/'apply.py','apply-kiss.py'),(header,'kiss_fft_log.candidate.h')]:
 subprocess.run(['scp.exe',*options,str(p),host+':'+dest+'/'+n],check=True)
subprocess.run(['ssh.exe',*options,host,'python3 '+dest+'/apply-kiss.py'],check=True)
for n in ('result.json','before.h','after.h'):
 subprocess.run(['scp.exe',*options,host+':'+dest+'/kiss-patch/'+n,str(O/n)],check=True)
s=(R/'tools/build_native_sherpa_asr1.py').read_text().replace('native-sherpa-asr-build1','native-sherpa-asr-build2').replace('compile-attempt1','compile-attempt2')
(R/'tools/build_native_sherpa_asr2.py').write_text(s)
