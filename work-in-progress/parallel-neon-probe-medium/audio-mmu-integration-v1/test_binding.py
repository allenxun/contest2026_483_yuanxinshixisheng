import pathlib,json,hashlib
from bind_elf import bind
p=pathlib.Path(__file__).resolve().parent;root=p.parents[2]
elf=root/'work-in-progress/parallel-cxx-unwind-medium/audio-rx-machine-review-v1/frozen-nuttx'
verify=root/'evidence/build/audio-mic-20260910/verification.json'
sdk=root/'evidence/audio-mmu-input-20260910'
result=bind(elf,verify,sdk)
assert result['xlat']['begin']=='0x4066d000' and result['base']['begin']=='0x40681000'
(p/'binding-reference-result.json').write_text(json.dumps(result,indent=2))
try:
 bind(elf,root/'evidence/build/audio-marker-20260910/verification.json',sdk)
 raise RuntimeError('mismatched ELF accepted')
except AssertionError:pass
records=[]
for f in [elf,verify,root/'evidence/build/audio-marker-20260910/verification.json']:
 records.append(dict(path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
(p/'binding-reference-inputs.json').write_text(json.dumps(records,indent=2))
print('PASS actual archived AArch64 ELF table ranges/identity/config/source binding')
print('PASS different build verification rejects old ELF')
print('Historical fixture only; do NOT execute its printed addresses on a new image')
