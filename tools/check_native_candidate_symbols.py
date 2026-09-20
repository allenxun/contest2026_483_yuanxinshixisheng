"""Read-only final ELF symbol audit; no board access or SDK writes."""
import json
from cloud_radio_stage_audit import ROOT, remote

code = '''import pathlib,subprocess,json,hashlib
p=pathlib.Path('/home/swl/openvela/cmake_out/velavision_native_photo_prompts_20260915')
b=(p/'nuttx.bin').read_bytes()
assert hashlib.sha256(b).hexdigest()=='8cbd147ad72a3b463e734ab42320d91d80219d2b978a6bdff6b83671011965d1'
symbols=subprocess.check_output(['nm',str(p/'nuttx')],text=True)
names={line.split()[-1] for line in symbols.splitlines() if line.split()}
required=['k7cloud_device_loop','k7cloud_device_stop','k7_photo_native_status','k7_photo_prompt_plan']
result={name:name in names for name in required}
print(json.dumps({'firmware_sha256':hashlib.sha256(b).hexdigest(),'symbols':result,'upload_copy_linked':'k7_photo_native_copy' in names,'hardware_tested':False}))
assert all(result.values()),result
'''
data = json.loads(remote(code))
out = ROOT / 'evidence/native-photo-prompts-20260915/symbol-audit.json'
out.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
print(json.dumps(data))
