import base64
from cloud_radio_stage_audit import ROOT,remote
files=['app/k7host/k7_photo_store.h','app/k7agent/cloud/src/board_speech_bridge.c','app/k7agent/cloud/src/board_voice_prompts.inc',
       'app/k7agent/cloud/include/device_photo_prompts.h','app/k7agent/cloud/src/device_photo_prompts.c',
       'app/k7agent/cloud/src/device_voice_intent.c','app/k7agent/cloud/include/device_voice_intent.h',
       'app/k7radio/cJSON.c','app/k7radio/cJSON.h','app/k7sound/capture_stream.h',
       'app/k7sound/pio.h','app/k7sound/stream_ring.h','app/k7sound/stream_ring.c',
       'host/whole_device/test_device_stop.c']
data={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in files}
print(remote('''import base64,pathlib,tempfile,subprocess
with tempfile.TemporaryDirectory() as folder:
 root=pathlib.Path(folder)
 for rel,raw in %r.items():
  p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(raw))
 for opt in ['-O0','-O2']:
  subprocess.run(['gcc','-std=c11','-D_DEFAULT_SOURCE','-DCONFIG_EXAMPLES_K7HOST_TRACK',opt,
   '-Wall','-Wextra','-Werror','-pthread','-Iapp/k7sound','-Iapp/k7agent/cloud/include',
   'host/whole_device/test_device_stop.c','app/k7sound/stream_ring.c',
   'app/k7agent/cloud/src/device_voice_intent.c','app/k7agent/cloud/src/device_photo_prompts.c','app/k7radio/cJSON.c','-lm','-o','test'],cwd=root,check=True)
  subprocess.run([str(root/'test')],check=True)
'''%data).decode())
