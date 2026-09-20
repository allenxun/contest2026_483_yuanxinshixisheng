"""Conservative check of the actual generated registration, never edits it."""
from pathlib import Path
import sys,re,hashlib
p=Path(sys.argv[1])
if not p.is_file():raise SystemExit('missing generated registration')
s=p.read_text()
# Strip C/C++ comments; any residual identifier is conservatively forbidden.
s=re.sub(r'/\*.*?\*/|//[^\n]*','',s,flags=re.S)
if 'BuildKernelCreateInfo' not in s or 'StringNormalizer' in s:
 raise SystemExit('not valid reduced registration or live StringNormalizer reference')
print('generated registration without StringNormalizer SHA256',hashlib.sha256(p.read_bytes()).hexdigest())
