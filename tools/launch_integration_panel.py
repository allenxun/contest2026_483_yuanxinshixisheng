"""Deploy reviewed host UI only and open the logged-in Ubuntu desktop."""
import base64,json,sys
from cloud_radio_stage_audit import ROOT,remote
files=['host/whole_device/integration_panel.py','host/vision/k7_video_receiver.py','host/vision/track_overlay.py']
payload={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in files}
code='''import pathlib,base64,hashlib,os,subprocess,json
root=pathlib.Path('/home/swl/openvela/work/velavision-project')
for rel,encoded in %r.items():
 p=root/rel;data=base64.b64decode(encoded)
 if p.exists() and p.read_bytes()!=data:
  old=p.read_bytes();backup=root/'evidence/integration-panel-20260916/before'/hashlib.sha256(old).hexdigest()/rel
  backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(old)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
env=dict(os.environ)
allowed={'DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'}
for proc in pathlib.Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  if proc.stat().st_uid!=os.getuid() or b'gnome-session-binary' not in (proc/'cmdline').read_bytes():continue
  for item in (proc/'environ').read_bytes().split(b'\\0'):
   key,sep,value=item.partition(b'=')
   if sep and key.decode(errors='replace') in allowed:env[key.decode()]=value.decode()
 except OSError:pass
out=root/'evidence/integration-panel-20260916';out.mkdir(parents=True,exist_ok=True)
with (out/'window-console.log').open('ab') as log:
 child=subprocess.Popen(['python3',str(root/'host/whole_device/integration_panel.py'),'--output',str(out)],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({'panel_pid':child.pid,'output':str(out),'auto_recording':False,'auto_motion':False}))
'''%payload
if '--connect' in sys.argv:
 code=code.replace("'--output',str(out)]", "'--output',str(out),'--connect']")
if '--report-task' in sys.argv:
 import uuid
 task=str(uuid.UUID(sys.argv[sys.argv.index('--report-task')+1]))
 code=code.replace("'--output',str(out)", "'--report-task',"+repr(task)+",'--output',str(out)")
if '--attach' in sys.argv:
 code=code.replace("'--connect']", "'--connect','--attach']")
if '--confirmed-camera' in sys.argv:
 if '--attach' in sys.argv:
  code=code.replace("'--attach']", "'--attach','--confirmed-camera']")
 else:
  code=code.replace("'--connect']", "'--connect','--confirmed-camera']")
if '--resume-camera' in sys.argv:
 if '--attach' in sys.argv:
  code=code.replace("'--attach']", "'--attach','--resume-camera']")
 else:
  code=code.replace("'--connect']", "'--connect','--resume-camera']")
if '--soak-telemetry' in sys.argv:
 code=code.replace("'--output',str(out)", "'--soak-telemetry','--camera-seconds','10800','--output',str(out)")
result=remote(code);folder=ROOT/'evidence/integration-panel-20260916';folder.mkdir(parents=True,exist_ok=True)
(folder/'launch.json').write_bytes(result);print(result.decode())
