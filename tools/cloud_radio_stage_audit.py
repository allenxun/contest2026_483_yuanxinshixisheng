"""Read-only SDK predecessor capture for the cloud radio integration."""
import base64
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/cloud-radio-build-20260914'
SSH = [r'C:\Windows\System32\OpenSSH\ssh.exe', '-i',
       'C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519',
       '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts',
       'swl@192.168.152.131']
FILES = ['app/k7agent/CMakeLists.txt', 'app/k7agent/Kconfig',
         'app/k7agent/cloud/src/k7cloud_main.c',
         'app/k7agent/cloud/include/cloud_speech_radio_bridge.h',
         'app/k7agent/cloud/src/cloud_speech_radio_bridge.c',
         'app/k7agent/cloud/src/cloud_speech_k7radio_sync.c',
         'app/k7radio/k7_radio_service.h', 'app/k7radio/wifi_ip_service.inc',
         'board/kickpi_k7/configs/velavision_cloud_speech_local/defconfig']

def remote(code):
    return subprocess.check_output(SSH + ['python3 -'], input=code.encode())

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    code = '''import pathlib,json,base64
root=pathlib.Path('/home/swl/openvela')
files=%r
result={}
for rel in files:
 dest=('apps/examples/'+rel[4:]) if rel.startswith('app/') else ('nuttx/boards/arm64/rk3576/'+rel[6:])
 p=root/dest
 result[rel]=base64.b64encode(p.read_bytes()).decode() if p.exists() else None
print(json.dumps(result))
''' % FILES
    data=json.loads(remote(code))
    report={}
    for rel, encoded in data.items():
        content=base64.b64decode(encoded) if encoded is not None else None
        if content is not None:
            dest=OUT/'sdk-before'/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.exists() and dest.read_bytes()!=content:
                raise RuntimeError('Refuse to replace predecessor: '+rel)
            dest.write_bytes(content)
        report[rel]={'sdk_sha256':hashlib.sha256(content).hexdigest() if content is not None else None,
                     'source_sha256':hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()}
    (OUT/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
