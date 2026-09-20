import base64
from cloud_radio_stage_audit import ROOT,remote
files=['app/k7host/k7_photo_store.c','app/k7host/k7_photo_store.h',
       'host/whole_device/test_photo_store.c']
data={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in files}
print(remote('''import base64,pathlib,tempfile,subprocess
with tempfile.TemporaryDirectory() as folder:
 root=pathlib.Path(folder)
 for rel,raw in %r.items():
  p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(raw))
 for opt in ['-O0','-O2']:
  subprocess.run(['gcc','-std=c11',opt,'-Wall','-Wextra','-Werror','-pthread',
   'host/whole_device/test_photo_store.c','app/k7host/k7_photo_store.c','-o','test'],cwd=root,check=True)
  subprocess.run([str(root/'test')],check=True)
'''%data).decode())
