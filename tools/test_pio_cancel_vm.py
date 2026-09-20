import base64
from cloud_radio_stage_audit import ROOT,remote
files=['host/whole_device/test_pio_cancel.c','app/k7sound/pio.c','app/k7sound/pio.h',
       'app/k7sound/input/rockchip_sai.h']
data={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in files}
print(remote('''import pathlib,tempfile,base64,subprocess
with tempfile.TemporaryDirectory(prefix='k7-pio-cancel-') as folder:
 root=pathlib.Path(folder)
 for rel,data in %r.items():
  p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(data))
 for opt in ['-O0','-O2']:
  subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',opt,'host/whole_device/test_pio_cancel.c','-o','test'],cwd=root,check=True)
  subprocess.run([str(root/'test')],check=True)
'''%data).decode())
