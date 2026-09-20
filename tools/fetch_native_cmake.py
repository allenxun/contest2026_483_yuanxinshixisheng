"""Acquire an isolated official CMake binary, verified against release digest."""
import hashlib,urllib.request,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'work-in-progress/native-voice-sources/build-tools';O.mkdir(exist_ok=True)
version='3.28.3';name='cmake-'+version+'-linux-x86_64.tar.gz'
base='https://github.com/Kitware/CMake/releases/download/v'+version+'/'
with urllib.request.urlopen(base+'cmake-'+version+'-SHA-256.txt',timeout=60) as response:
    checks=response.read(1024*1024).decode('ascii')
expected=next(line.split()[0] for line in checks.splitlines() if line.split()[-1]==name)
target=O/name
if not target.exists():
    with urllib.request.urlopen(base+name,timeout=60) as response:
        data=response.read(100*1024*1024+1)
    assert len(data)<=100*1024*1024 and hashlib.sha256(data).hexdigest()==expected
    with target.open('xb') as stream:stream.write(data)
else:assert hashlib.sha256(target.read_bytes()).hexdigest()==expected
(O/'cmake-source.json').write_text(json.dumps(dict(version=version,url=base+name,
    sha256=expected,checksum_source=base+'cmake-'+version+'-SHA-256.txt',installed_globally=False),indent=2))
(O/'cmake-SHA-256.txt').write_text(checks)
print(name,expected,flush=True)
