"""Prepare actual recognizer symbol closure audit; no speech-ready claim."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tools/audit_native_session_link2.py').read_text()
s=s.replace('native-session-link2','native-sherpa-link1')
s=s.replace("O=S/'link-attempt2'","O=Path('/home/swl/openvela/work/native-sherpa-config2-20260911/link1')")
s=s.replace("archives=sorted((S/'build').rglob('*.a'))","ASR=Path('/home/swl/openvela/work/native-sherpa-config2-20260911')\nassert json.loads((ASR/'compile-attempt2/result.json').read_text())['exit_code']==0\narchives=sorted((S/'build').rglob('*.a'))+sorted((ASR/'build').rglob('*.a'))")
s=s.replace("cmd=[ld,'-r','--strip-debug'","cmd=[ld,'-r','--undefined=SherpaOnnxCreateOnlineRecognizer','--strip-debug'")
s=s.replace("firmware_linked=False,model_run=False)","firmware_linked=False,model_run=False,asr_ready=False,ort_kernel_set='Add-only; symbol inventory only')")
s=s.replace('audit-session.py','audit-sherpa-capi.py')
s=s.replace("host+':'+dest+'/link-attempt2/results.tar.gz'","host+':/home/swl/openvela/work/native-sherpa-config2-20260911/link1/results.tar.gz'")
p=R/'tools/audit_native_sherpa_link1.py';assert not p.exists();p.write_text(s)
