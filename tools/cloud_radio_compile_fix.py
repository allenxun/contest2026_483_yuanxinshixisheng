"""Apply the missing radio snapshot header after checking the staged hash."""
import base64,json
from cloud_radio_stage_audit import ROOT,OUT,remote
rel='app/k7radio/wifi_ip_service.inc'
expected=json.loads((OUT/'audit.json').read_text())[rel]['source_sha256']
payload=base64.b64encode((ROOT/rel).read_bytes()).decode()
code='''import pathlib,hashlib,base64,subprocess
sdk=pathlib.Path('/home/swl/openvela')
root=sdk/'work/velavision-project'
target=sdk/'apps/examples/k7radio/wifi_ip_service.inc'
assert hashlib.sha256(target.read_bytes()).hexdigest()==%r
data=base64.b64decode(%r)
(root/%r).write_bytes(data)
target.write_bytes(data)
ev=root/'evidence/cloud-radio-build-20260914'
with (ev/'arm64-build-retry.log').open('xb') as log:
 p=subprocess.Popen(['bash','-c','source build/envsetup.sh >/dev/null && prebuilts/tools/cmake/bin/cmake --build cmake_out/velavision_cloud_radio_20260914 -j4'],cwd=str(sdk),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(p.pid)
''' % (expected,payload,rel)
print(remote(code).decode())
