"""Stage pinned full CPU runtime sources; never run or modify target firmware."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];B=R/'work-in-progress/native-voice-sources'
ORT=B/'onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d'
P=R/'private/native-ort-session-stage';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-session-20260911';O.mkdir(exist_ok=True)
manifest={}
with tarfile.open(P/'stage.tar.gz','w:gz') as tar:
 for p in sorted(ORT.rglob('*')):
  if not p.is_file():continue
  rel=p.relative_to(ORT)
  if rel.parts[0] not in ('cmake','include','onnxruntime','tools') and len(rel.parts)>1:continue
  if rel.parts[:2]==('onnxruntime','test'):continue
  if p.suffix in ('.onnx','.ort','.pb','.png','.jpg','.gif','.ipynb'):continue
  dest='ort/'+rel.as_posix()
  manifest[dest]=hashlib.sha256(p.read_bytes()).hexdigest();tar.add(p,arcname=dest)
 for name in ('abseil_cpp','date','microsoft_gsl','safeint','google_nsync','flatbuffers','json','mp11','onnx','protobuf','re2','utf8_range','protoc_linux_x64'):
  p=B/'deps'/(name+'.zip');meta=json.loads(p.with_suffix('.json').read_text())
  assert hashlib.sha256(p.read_bytes()).hexdigest()==meta['sha256']
  tar.add(p,arcname='deps/'+p.name);manifest['deps/'+p.name]=meta['sha256']
 overrides={
 'ort/onnxruntime/core/platform/posix/env.cc':R/'work-in-progress/parallel-model-reader-medium/env-gate-v2/env-gate.cc',
 'ort/onnxruntime/core/common/logging/logging.cc':R/'work-in-progress/parallel-model-reader-medium/logging-nuttx-v1/logging.cc',
 'abseil-elf.h':R/'work-in-progress/parallel-model-reader-medium/native-abseil-nuttx-debug-v1/elf_mem_image.h'}
 for dest,p in overrides.items():
  # Separate override entries preserve the original input file's manifest hash.
  key='overrides/'+dest;manifest[key]=hashlib.sha256(p.read_bytes()).hexdigest();tar.add(p,arcname=key)
 (O/'inputs.json').write_text(json.dumps(manifest,indent=2))
 tar.add(O/'inputs.json',arcname='inputs.json')
remote=r'''
import hashlib,json,zipfile,shutil,subprocess
from pathlib import Path
S=Path('/dev/shm/velavision-ort-session-20260911')
manifest=json.loads((S/'inputs.json').read_text())
for rel,digest in manifest.items():assert hashlib.sha256((S/rel).read_bytes()).hexdigest()==digest,rel
for archive in sorted((S/'deps').glob('*.zip')):
 destination=S/'sources'/archive.stem;destination.mkdir(parents=True)
 with zipfile.ZipFile(archive) as z:
  for member in z.infolist():
   parts=member.filename.split('/')
   if archive.stem!='protoc_linux_x64':parts=parts[1:]
   rel=Path(*parts)
   assert not rel.is_absolute() and '..' not in rel.parts
   if member.is_dir():continue
   mode=(member.external_attr>>16)&0o170000
   if mode==0o120000:continue
   output=destination/rel;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(z.read(member))
for rel in ('ort/onnxruntime/core/platform/posix/env.cc','ort/onnxruntime/core/common/logging/logging.cc'):
 shutil.copyfile(S/'overrides'/rel,S/rel)
shutil.copyfile(S/'overrides/abseil-elf.h',S/'sources/abseil_cpp/absl/debugging/internal/elf_mem_image.h')
protoc=S/'sources/protoc_linux_x64/bin/protoc';protoc.chmod(0o755)
version=subprocess.check_output([str(protoc),'--version'],text=True).strip()
assert version=='libprotoc 3.21.12',version
(S/'stage-result.json').write_text(json.dumps(dict(input_files=len(manifest),protoc_version=version,configured=False),indent=2))
print(version,len(manifest),'files verified',flush=True)
'''
(P/'stage.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-session-20260911'
def call(args):subprocess.run(args,check=True)
call(['ssh.exe',*options,host,'mkdir '+dest])
call(['scp.exe',*options,str(P/'stage.tar.gz'),str(P/'stage.py'),host+':'+dest+'/'])
call(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && python3 stage.py'])
call(['scp.exe',*options,host+':'+dest+'/stage-result.json',str(O/'stage-result.json')])
