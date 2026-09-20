"""Transfer verified offline ASR sources to independent tmpfs, without building."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R/'work-in-progress/parallel-model-reader-medium/native-sherpa-offline-stage-v1'
S=R/'work-in-progress/native-voice-sources/sherpa-onnx-26aa2fa93210376a89de3a65a1a4dd320c37f5e9'
P=R/'private/native-sherpa-asr-stage';P.mkdir(exist_ok=True)
O=R/'evidence/native-sherpa-asr-stage-20260911';O.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest={}
with tarfile.open(P/'stage.tar.gz','w:gz') as tar:
    for rel,record in json.loads((C/'source-manifest.json').read_text()).items():
        p=C/rel
        assert sha(p)==record['sha256'] and p.stat().st_size==record['bytes'],rel
        dest=rel.replace('\\','/')
        info=tar.gettarinfo(str(p),arcname=dest)
        info.mode=int(record['mode'],8)
        with p.open('rb') as f:tar.addfile(info,f)
        manifest[dest]=record['sha256']
    for p in sorted(S.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(S)
        # Preserve implementation, CMake and licenses; no examples or test media.
        if rel.parts[0] not in ('cmake','sherpa-onnx') and len(rel.parts)>1:continue
        if p.suffix in ('.wav','.onnx','.ort','.png','.jpg'):continue
        dest='sherpa/'+rel.as_posix()
        tar.add(p,arcname=dest);manifest[dest]=sha(p)
    for name in ('candidate.patch','onnxruntime-nuttx.cmake','asr-initial-cache.cmake'):
        p=C/name;dest='candidate/'+name
        tar.add(p,arcname=dest);manifest[dest]=sha(p)
    (O/'inputs.json').write_text(json.dumps(manifest,indent=2))
    tar.add(O/'inputs.json',arcname='inputs.json')
remote=r'''
import hashlib,json,subprocess
from pathlib import Path
S=Path('/dev/shm/velavision-sherpa-asr-20260911')
m=json.loads((S/'inputs.json').read_text())
for rel,h in m.items():assert hashlib.sha256((S/rel).read_bytes()).hexdigest()==h,rel
patch=S/'candidate/candidate.patch'
patch.write_text(patch.read_text())
for cmd in (['git','apply','--check',str(patch)],['git','apply',str(patch)]):
 p=subprocess.run(cmd,cwd=S/'sherpa',stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 assert p.returncode==0,p.stdout
(S/'sherpa/cmake/onnxruntime-nuttx.cmake').write_bytes((S/'candidate/onnxruntime-nuttx.cmake').read_bytes())
result=dict(input_count=len(m),inputs_checked=True,patch_applied=True,configured=False,compiled=False,
 import_sha256=hashlib.sha256((S/'sherpa/cmake/onnxruntime-nuttx.cmake').read_bytes()).hexdigest())
(S/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result),flush=True)
'''
(P/'stage.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-sherpa-asr-20260911'
subprocess.run(['ssh.exe',*options,host,'mkdir '+dest],check=True)
subprocess.run(['scp.exe',*options,str(P/'stage.tar.gz'),str(P/'stage.py'),host+':'+dest+'/'],check=True)
subprocess.run(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && python3 stage.py'],check=True)
subprocess.run(['scp.exe',*options,host+':'+dest+'/result.json',str(O/'result.json')],check=True)
