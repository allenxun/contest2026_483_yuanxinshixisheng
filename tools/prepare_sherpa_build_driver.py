"""Derive a separate reproducible ASR library build, keeping ORT evidence intact."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tools/build_native_ort_session6.py').read_text()
s=s.replace('native-ort-session-build6','native-sherpa-asr-build1').replace('native-sherpa-asr-build11-20260911','native-sherpa-asr-build1-20260911')
s=s.replace('/dev/shm/velavision-ort-session-20260911','/home/swl/openvela/work/native-sherpa-config2-20260911').replace('compile-attempt6','compile-attempt1')
begin=s.index("targets=['onnxruntime_session'");end=s.index('\ncmd=',begin)
s=s[:begin]+"targets=['sherpa-onnx-c-api']"+s[end:]
p=R/'tools/build_native_sherpa_asr1.py';assert not p.exists();p.write_text(s)
