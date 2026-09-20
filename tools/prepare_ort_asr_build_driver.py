"""Create separate ASR runtime build with bounded process-group cleanup."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tools/build_native_ort_session6.py').read_text()
s=s.replace('native-ort-session-build6','native-ort-asr-build1').replace('native-ort-asr-build11-20260911','native-ort-asr-build1-20260911')
s=s.replace('/dev/shm/velavision-ort-session-20260911','/home/swl/openvela/work/native-ort-asr-20260911').replace('compile-attempt6','compile-attempt1')
s=s.replace('import hashlib,json,shlex,subprocess,tarfile,time','import hashlib,json,shlex,subprocess,tarfile,time,os,signal')
s=s.replace("'onnxruntime_common','onnxruntime_flatbuffers']","'onnxruntime_common','onnxruntime_flatbuffers','nsync_cpp']")
old="  p=subprocess.run(['bash','-c','cd /home/swl/openvela && source build/envsetup.sh >/dev/null && '+shlex.join(cmd)],stdout=stream,stderr=subprocess.STDOUT,timeout=1200)\n  code=p.returncode\nexcept subprocess.TimeoutExpired:timeout=True"
new="  p=subprocess.Popen(['bash','-c','cd /home/swl/openvela && source build/envsetup.sh >/dev/null && '+shlex.join(cmd)],stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)\n  try:code=p.wait(timeout=2400)\n  except subprocess.TimeoutExpired:\n   timeout=True;os.killpg(p.pid,signal.SIGTERM)\n   try:p.wait(timeout=10)\n   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()\nexcept subprocess.TimeoutExpired:timeout=True"
assert old in s;s=s.replace(old,new)
p=R/'tools/build_native_ort_asr1.py';assert not p.exists();p.write_text(s)
