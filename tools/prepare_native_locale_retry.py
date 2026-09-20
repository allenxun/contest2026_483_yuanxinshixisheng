"""Keep failed conservative check; permit only the exact unused forward declaration."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
V=R/'work-in-progress/native-locale-registration-check'
V.mkdir(exist_ok=True)
(V/'k7_verify_no_string_normalizer.py').write_text('''from pathlib import Path
import sys,re,hashlib
p=Path(sys.argv[1])
s=p.read_text()
s=re.sub(r'/\\*.*?\\*/|//[^\\n]*','',s,flags=re.S)
declaration='class ONNX_OPERATOR_KERNEL_CLASS_NAME(kCpuExecutionProvider, kOnnxDomain, 10, StringNormalizer);'
assert s.count(declaration)==1, 'unexpected declaration shape'
s=s.replace(declaration,'')
assert 'BuildKernelCreateInfo' in s and 'StringNormalizer' not in s, 'live reference remains'
print('Only exact unused declaration; no live registration',hashlib.sha256(p.read_bytes()).hexdigest())
''')
src=(R/'tools/resume_native_session_reduced_locale.py').read_text()
src=src.replace("native-ort-reduced-locale'","native-ort-reduced-locale2'")
src=src.replace('native-ort-reduced-locale-20260911','native-ort-reduced-locale2-20260911')
src=src.replace("O=S/'locale-config'","O=S/'locale-config2'")
src=src.replace("'/locale-config/results.tar.gz'","'/locale-config2/results.tar.gz'")
src=src.replace("(C/'k7_verify_no_string_normalizer.py','k7_verify_no_string_normalizer.py')",
                "(R/'work-in-progress/native-locale-registration-check/k7_verify_no_string_normalizer.py','k7_verify_no_string_normalizer.py')")
(R/'tools/resume_native_session_reduced_locale2.py').write_text(src)
