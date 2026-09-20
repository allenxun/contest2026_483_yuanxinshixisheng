from pathlib import Path
import hashlib
R=Path(__file__).resolve().parents[1]
s=(R/'tools/configure_native_ort_session3.py').read_text().replace('native-ort-session-config3','native-ort-session-config4').replace('config-attempt3','config-attempt4')
rel='orttraining/orttraining/training_ops/cpu/cpu_training_kernels.cc'
p=R/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d'/rel
digest=hashlib.sha256(p.read_bytes()).hexdigest()
s=s.replace("records=[]", "records=[]\nassert hashlib.sha256((S/'ort/"+rel+"').read_bytes()).hexdigest()=='"+digest+"'")
s=s.replace("tar.add(P/'configure.py',arcname='configure.py')", "tar.add(P/'configure.py',arcname='configure.py')\n tar.add(R/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d/"+rel+"',arcname='ort/"+rel+"')")
target=R/'tools/configure_native_ort_session4.py';assert not target.exists()
compile(s,str(target),'exec');target.write_text(s)
