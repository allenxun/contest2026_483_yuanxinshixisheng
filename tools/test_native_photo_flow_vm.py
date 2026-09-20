import base64
from cloud_radio_stage_audit import ROOT,remote
files=['app/k7host/'+n for n in ['k7_photo.c','k7_photo.h','k7_photo_store.c','k7_photo_store.h',
       'k7_pose.h','k7_jpeg.h','k7_track.h','k7_yunet.h','fusion_core.c','fusion_core.h']]
files+=['host/whole_device/test_native_photo_flow.c']
data={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in files}
print(remote('''import base64,pathlib,tempfile,subprocess
with tempfile.TemporaryDirectory() as folder:
 root=pathlib.Path(folder)
 for rel,raw in %r.items():
  p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(raw))
 for opt in ['-O0','-O2']:
  subprocess.run(['gcc','-std=c11','-D_POSIX_C_SOURCE=200809L',opt,
   '-Wall','-Wextra','-Werror','-pthread','host/whole_device/test_native_photo_flow.c',
   'app/k7host/fusion_core.c','app/k7host/k7_photo_store.c','-lm','-o','test'],cwd=root,check=True)
  result=subprocess.run([str(root/'test')],capture_output=True,text=True)
  print(result.stdout[-1500:]);print(result.stderr);result.check_returncode()
'''%data).decode())
