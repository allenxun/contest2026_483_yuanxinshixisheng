"""Compile actual mode code in isolated Ubuntu temp dir; no SDK/board writes."""
import base64
import json
from pathlib import Path
from cloud_radio_stage_audit import remote

ROOT = Path(__file__).resolve().parents[1]
files = ['app/k7host/k7_photo_target.h', 'host/whole_device/test_voice_mode.c', 'app/k7host/k7_pipeline.c',
         'app/k7host/k7_pipeline.h', 'app/k7host/k7_track.c',
         'app/k7host/k7_track.h', 'app/k7host/k7_jpeg.h',
         'app/k7host/k7_yunet.h', 'app/k7host/k7_preview.h',
         'app/k7host/k7_photo.h', 'app/k7host/k7_photo_store.h', 'app/gimbal/gimbal_link.h']
data = {name: base64.b64encode((ROOT/name).read_bytes()).decode() for name in files}
code = '''import base64,pathlib,tempfile,subprocess,json
data=%r
with tempfile.TemporaryDirectory(prefix='k7-voice-mode-') as folder:
 root=pathlib.Path(folder)
 for name,encoded in data.items():
  dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_bytes(base64.b64decode(encoded))
 for opt in ['-O0','-O2']:
  args=['gcc','-std=c11','-D_POSIX_C_SOURCE=200809L','-DCONFIG_EXAMPLES_K7HOST_TRACK',
        '-DCONFIG_EXAMPLES_K7HOST_YUNET',opt,'-Wall','-Wextra','-Werror',
        '-ffunction-sections','-fdata-sections','host/whole_device/test_voice_mode.c',
        'app/k7host/k7_track.c','-Wl,--gc-sections','-pthread','-lm','-o','test-mode']
  subprocess.run(args,cwd=root,check=True)
  subprocess.run([str(root/'test-mode')],cwd=root,check=True)
print('O0/O2 actual firmware mode tests passed; no hardware accessed')
''' % data
print(remote(code).decode())
