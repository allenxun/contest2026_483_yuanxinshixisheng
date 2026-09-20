"""Prepare recognizer linkage with the new ASR, not Add-only, ORT libraries."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tools/audit_native_sherpa_link2.py').read_text().replace('native-sherpa-link2','native-asr-link3').replace('/link2','/link3').replace('audit-sherpa-capi2.py','audit-real-asr.py')
s=s.replace('velavision-native-add-probe-20260911','velavision-native-asr-add-probe-20260911')
old="archives=sorted((S/'build').rglob('*.a'))+sorted((ASR/'build').rglob('*.a'))"
new="ORT_ASR=Path('/home/swl/openvela/work/native-ort-asr-20260911')\nassert json.loads((ORT_ASR/'compile-attempt1/result.json').read_text())['exit_code']==0\narchives=sorted((ORT_ASR/'build').rglob('*.a'))+sorted((ASR/'build').rglob('*.a'))"
assert old in s;s=s.replace(old,new).replace("ort_kernel_set='Add-only; symbol inventory only'","ort_kernel_set='28-entry ASR config; inference untested'")
p=R/'tools/audit_native_asr_link3.py';assert not p.exists();p.write_text(s)
