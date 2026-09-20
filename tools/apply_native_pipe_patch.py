"""Apply one exact reviewed header to isolated dependency stage; preserve input."""
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=R/'private/native-pipe-patch';P.mkdir(exist_ok=True)
O=R/'evidence/native-pipe-patch-20260911';O.mkdir(exist_ok=True)
header=R/'work-in-progress/parallel-model-reader-medium/native-kaldifst-no-pipe-v1/kaldi-io.cc'
assert hashlib.sha256(header.read_bytes()).hexdigest()=='461f5b15450ef30f1c4253b89b009a6f79361000e4e5bf2aa46963eed7a6c24a'
remote=r'''
import hashlib,json
from pathlib import Path
S=Path('/home/swl/openvela/work/native-sherpa-config2-20260911')
O=S/'pipe-patch';O.mkdir()
p=Path('/home/swl/openvela/work/native-sherpa-config2-20260911/sources/kaldifst/kaldifst/csrc/kaldi-io.cc')
old=p.read_bytes();new=(S/'kaldi-io.candidate.cc').read_bytes()
assert hashlib.sha256(old).hexdigest()=='b87dae3202f3a7e8d4b576f10d1b7ea74da9fa236c7a581f4ffe067331222cc2'
assert hashlib.sha256(new).hexdigest()=='461f5b15450ef30f1c4253b89b009a6f79361000e4e5bf2aa46963eed7a6c24a'
(O/'before.h').write_bytes(old);p.write_bytes(new);(O/'after.h').write_bytes(new)
(O/'result.json').write_text(json.dumps(dict(path=str(p),before=hashlib.sha256(old).hexdigest(),after=hashlib.sha256(p.read_bytes()).hexdigest(),scope='isolated staged dependency only'),indent=2))
print('PATCHED_EXACT_HEADER')
'''
(P/'apply.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/native-sherpa-config2-20260911'
for p,n in [(P/'apply.py','apply-pipe.py'),(header,'kaldi-io.candidate.cc')]:
 subprocess.run(['scp.exe',*options,str(p),host+':'+dest+'/'+n],check=True)
subprocess.run(['ssh.exe',*options,host,'python3 '+dest+'/apply-pipe.py'],check=True)
for n in ('result.json','before.h','after.h'):
 subprocess.run(['scp.exe',*options,host+':'+dest+'/pipe-patch/'+n,str(O/n)],check=True)
s=(R/'tools/build_native_sherpa_asr2.py').read_text().replace('native-sherpa-asr-build2','native-sherpa-asr-build3').replace('compile-attempt2','compile-attempt3')
(R/'tools/build_native_sherpa_asr3.py').write_text(s)
