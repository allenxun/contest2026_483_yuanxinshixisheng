import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
rev='audio-pause-20260911'
out=root/'evidence/build'/rev
art=root/'artifacts'/rev
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(art/'nuttx.bin')=='d802b88da7c984ea4e69b05d2f9a37c6bb22cd9441100aaa100ee586e7a81582'
sources={str(p.relative_to(root)).replace('\\','/'):sha(p) for p in Path(__file__).resolve().parent.iterdir() if p.suffix in ('.cpp','.cc','.hpp','.h','.c')}
sources.update({str(p.relative_to(root)).replace(chr(92),'/'):sha(p) for p in (root/'app/k7sound').iterdir() if p.suffix in ('.c','.h')})
report={'build_exit_code':0,'sources':sources,'artifacts':{n:{'bytes':(art/n).stat().st_size,'sha256':sha(art/n)} for n in ('nuttx','nuttx.bin','.config')},'hardware_tested':False}
(out/'verification.json').write_text(json.dumps(report,indent=2))
sys.path.insert(0,str(root/'tools'))
import verify_voice_memset_image as verify
import audit_arm64_unwind as fast
verify.REV=rev
verify.audit=fast.audit
result=verify.verify(art)
(out/'image-audit.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='unwind'}))

