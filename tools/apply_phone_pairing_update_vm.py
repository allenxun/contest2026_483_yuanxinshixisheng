"""Refuse unknown mirror changes before applying the explicit phone fix bundle."""
import hashlib,json,tarfile
from pathlib import Path
root=Path('/home/swl/openvela/work/velavision-project')
bundle=Path('/home/swl/openvela/work/phone-pairing-update')
manifest=json.loads((bundle/'manifest.json').read_text())
writes=[]
with tarfile.open(bundle/'update.tar.gz') as archive:
    for member in archive.getmembers():
        assert member.isfile() and member.name in manifest
        dest=(root/member.name).resolve();assert dest.is_relative_to(root)
        blob=archive.extractfile(member).read();expected=manifest[member.name]
        assert hashlib.sha256(blob).hexdigest()==expected['new']
        if dest.exists():
            digest=hashlib.sha256(dest.read_bytes()).hexdigest()
            if digest not in expected['previous']+[expected['new']]:raise RuntimeError('Unknown mirror change: '+member.name)
        writes.append((dest,blob))
assert len(writes)==len(manifest)
for dest,blob in writes:
    dest.parent.mkdir(exist_ok=True,parents=True);dest.write_bytes(blob)
print('Guarded mirror update PASS:',len(writes))
