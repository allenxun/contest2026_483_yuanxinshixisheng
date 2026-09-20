"""Assemble reviewed radio candidate in private staging; never touch SDK/board."""
import hashlib
import json
import re
import shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1]
B=R/'work-in-progress/parallel-model-reader-medium'
versions=[('voice-radio-backend-v1','820d5a9a68faecabc8e60eaed2218e8f31224b347a3df3d3e0ce55306d42d3d5'),
 ('voice-radio-backend-review-v1','f007f3a76207d29688fcb1945752a82b2cafd3f1175f04c6ae2f537e081041fc'),
 ('voice-radio-backend-review-v2','d52bbc991af0af5b5a6359c826ed18a5fb685292584ec69e7a39f42aa933289b')]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name,want in versions:
    d=B/name
    assert sha(d/'outputs.json')==want
    for f in json.loads((d/'outputs.json').read_text()):
        assert sha(d/f.get('path',f.get('name')))==f['sha256']
S=R/'private/radio-reviewed-stage-20260910'
assert not S.exists(), 'Staging already exists; do not overwrite'
original={p.relative_to(R/'app/k7radio').as_posix():sha(p) for p in (R/'app/k7radio').rglob('*') if p.is_file()}
shutil.copytree(R/'app/k7radio',S/'app/k7radio')
v1=B/versions[0][0]
paths=re.findall(r'^\+\+\+ b/app/k7radio/(\S+)$',(v1/'candidate.patch').read_text(),re.M)
provenance={}
for name in paths:
    src=v1/'candidate'/name
    if not src.exists():src=v1/name
    assert src.is_file(), name
    (S/'app/k7radio'/name).write_bytes(src.read_bytes())
    provenance[name]=src.relative_to(R).as_posix()
for name in ('prov_service.inc','radio_backend.inc','radio_backend_state.inc'):
    src=B/versions[1][0]/name
    (S/'app/k7radio'/name).write_bytes(src.read_bytes())
    provenance[name]=src.relative_to(R).as_posix()
src=B/versions[2][0]/'CMakeLists.txt'
(S/'app/k7radio/CMakeLists.txt').write_bytes(src.read_bytes())
provenance['CMakeLists.txt']=src.relative_to(R).as_posix()
for name,digest in original.items():assert sha(R/'app/k7radio'/name)==digest
report=dict(formal_source_unchanged=True,sdk_compiled=False,hardware_tested=False,
    inputs=original,candidate_manifests=dict(versions),provenance=provenance,
    files={p.relative_to(S).as_posix():sha(p) for p in S.rglob('*') if p.is_file()})
(S/'assembly.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Reviewed backend staged; formal source unchanged; SDK integration pending')
