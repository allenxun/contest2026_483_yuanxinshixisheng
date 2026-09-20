"""Fix the second vendor range-copy warning in the isolated source tree."""
import json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
O=R/'evidence/native-ort-session-range-loop-20260911';O.mkdir(exist_ok=False)
script=r'''
import hashlib,json
from pathlib import Path
s=Path('/dev/shm/velavision-ort-session-20260911')
assert json.loads((s/'compile-attempt5/result.json').read_text())['exit_code']==1
p=s/'ort/onnxruntime/core/session/inference_session.cc'
b=p.read_bytes();text=b.decode()
old='for (const auto op_schema : saved_runtime_optimization_produced_node_op_schemas_)'
assert text.count(old)==1
out=s/'range-loop-fix';out.mkdir()
(out/'before.cc').write_bytes(b)
p.write_text(text.replace(old,'for (const auto& op_schema : saved_runtime_optimization_produced_node_op_schemas_)'))
(out/'after.cc').write_bytes(p.read_bytes())
result=dict(path=str(p),before_sha256=hashlib.sha256(b).hexdigest(),after_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
(out/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
'''
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
p=subprocess.run(['ssh.exe',*options,'swl@192.168.152.131','python3 -'],input=script,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(O/'patch.log').write_text(p.stdout)
assert p.returncode==0,p.stdout
(O/'result.json').write_text(json.dumps(json.loads(p.stdout),indent=2))
print(p.stdout)
for name in ('build_native_ort_session5.py',):
    s=(R/'tools'/name).read_text().replace('native-ort-session-build5','native-ort-session-build6').replace('compile-attempt5','compile-attempt6')
    (R/'tools/build_native_ort_session6.py').write_text(s)
for name in ('audit_native_session_link.py','configure_native_sherpa_asr.py'):
    p=R/'tools'/name
    p.write_text(p.read_text().replace('compile-attempt5/result.json','compile-attempt6/result.json'))
