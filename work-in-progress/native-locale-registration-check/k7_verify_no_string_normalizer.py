from pathlib import Path
import sys,re,hashlib
p=Path(sys.argv[1])
s=p.read_text()
s=re.sub(r'/\*.*?\*/|//[^\n]*','',s,flags=re.S)
declaration='class ONNX_OPERATOR_KERNEL_CLASS_NAME(kCpuExecutionProvider, kOnnxDomain, 10, StringNormalizer);'
assert s.count(declaration)==1, 'unexpected declaration shape'
s=s.replace(declaration,'')
assert 'BuildKernelCreateInfo' in s and 'StringNormalizer' not in s, 'live reference remains'
print('Only exact unused declaration; no live registration',hashlib.sha256(p.read_bytes()).hexdigest())
