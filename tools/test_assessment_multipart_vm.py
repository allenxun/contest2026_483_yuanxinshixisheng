import base64
from cloud_radio_stage_audit import ROOT,remote
files=['app/k7agent/cloud/include/assessment_multipart.h','app/k7agent/cloud/src/assessment_multipart.c',
       'host/whole_device/test_assessment_multipart.c']
data={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in files}
print(remote('''import base64,pathlib,tempfile,subprocess,json
from email.parser import BytesParser
from email.policy import default
with tempfile.TemporaryDirectory() as folder:
 root=pathlib.Path(folder)
 for rel,raw in %r.items():
  p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(raw))
 for opt in ['-O0','-O2']:
  subprocess.run(['gcc','-std=c11',opt,'-Wall','-Wextra','-Werror','-Iapp/k7agent/cloud/include',
   'host/whole_device/test_assessment_multipart.c','app/k7agent/cloud/src/assessment_multipart.c','-o','test'],cwd=root,check=True)
  subprocess.run([str(root/'test')],cwd=root,check=True)
  body=(root/'multipart.bin').read_bytes()
  msg=BytesParser(policy=default).parsebytes(b'Content-Type: multipart/form-data; boundary=K7-0123456789abcdef0123456789abcdef\\r\\n\\r\\n'+body)
  parts=list(msg.iter_parts());assert len(parts)==4
  assert [p.get_param('name',header='content-disposition') for p in parts]==['metadata','front','left','right']
  assert json.loads(parts[0].get_payload(decode=True))==dict(photoVersion='1',captureSessionId='capture',consentEvidenceRef='consent')
  assert parts[0].get_content_type()=='application/json'
  for p in parts[1:]:
   assert p.get_content_type()=='image/jpeg';assert p.get_payload(decode=True)==bytes([255,216,0,1,2,255,217])
 print('Independent MIME parser verified exact metadata/front/left/right; no backend request')
'''%data).decode())
