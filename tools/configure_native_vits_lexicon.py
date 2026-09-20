"""Configure reviewed optional VITS path in a new source/build snapshot."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R.parent/'worktrees/VelaVision-audio-noise/work-in-progress/native-vits-lexicon-only-v1'
P=R/'private/native-vits-lexicon';P.mkdir(exist_ok=True)
O=R/'evidence/native-vits-lexicon-config1-20260911';O.mkdir(exist_ok=True)
changes=json.loads((C/'changes.json').read_text())
with tarfile.open(P/'stage.tar.gz','w:gz') as t:
 t.add(C/'changes.json',arcname='changes.json')
 for row in changes:
  p=C/'candidate'/row['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['after_sha256']
  t.add(p,arcname='candidate/'+row['path'])
remote=r'''
import hashlib,json,shlex,subprocess,shutil,tarfile
from pathlib import Path
S=Path('/home/swl/openvela/work/native-vits-lexicon-20260911');O=S/'config1';O.mkdir()
old=Path('/dev/shm/velavision-sherpa-asr-20260911/sherpa')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs={str(p.relative_to(old)):sha(p) for p in old.rglob('*') if p.is_file()}
(O/'source-before.json').write_text(json.dumps(inputs,indent=2))
new=S/'sherpa';shutil.copytree(old,new)
changes=json.loads((S/'changes.json').read_text())
for row in changes:
 p=new/row['path'];expected=row['before_sha256']
 assert (sha(p)==expected) if expected is not None else not p.exists(),row['path']
 source=S/'candidate'/row['path'];assert sha(source)==row['after_sha256']
 p.write_bytes(source.read_bytes())
assert all(sha(old/n)==h for n,h in inputs.items()),'ASR source changed'
cmd=json.loads(Path('/home/swl/openvela/work/native-sherpa-config2-20260911/result/result.json').read_text())['command']
cmd[cmd.index('-S')+1]=str(new);cmd[cmd.index('-B')+1]=str(S/'build')
cmd+=['-DSHERPA_ONNX_ENABLE_TTS=ON','-DSHERPA_ONNX_TTS_VITS_LEXICON_ONLY=ON']
q=subprocess.run(['bash','-c','cd /home/swl/openvela && source build/envsetup.sh >/dev/null && '+shlex.join(cmd)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
(O/'configure.log').write_bytes(q.stdout)
result=dict(exit_code=q.returncode,command=cmd,changes=changes,compiled=False,model_run=False,far_memory_resolved=False)
if q.returncode==0:
 cc=json.loads((S/'build/compile_commands.json').read_text())
 forbidden=('piper-phonemize','espeak-ng','cppinyin','piper-phonemize-lexicon.cc','melo-tts-lexicon.cc')
 assert not any(any(x in c['file'] for x in forbidden) for c in cc)
 assert any(c['file'].endswith('/offline-tts-vits-model.cc') for c in cc)
 result['lexicon_source_selection_checked']=True
(O/'result.json').write_text(json.dumps(result,indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as t:
 for p in O.iterdir():
  if p.suffix in ('.json','.log'):t.add(p,arcname=p.name)
 if (S/'build/CMakeCache.txt').exists():t.add(S/'build/CMakeCache.txt',arcname='CMakeCache.txt')
print('VITS_CONFIG',q.returncode,flush=True);print(q.stdout.decode(errors='replace')[-1600:],flush=True)
'''
(P/'configure.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/native-vits-lexicon-20260911'
subprocess.run(['ssh.exe',*options,host,'mkdir '+dest],check=True)
for p,n in [(P/'stage.tar.gz','stage.tar.gz'),(P/'configure.py','configure.py')]:
 subprocess.run(['scp.exe',*options,str(p),host+':'+dest+'/'+n],check=True)
subprocess.run(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && python3 configure.py'],check=True)
subprocess.run(['scp.exe',*options,host+':'+dest+'/config1/results.tar.gz',str(P/'results.tar.gz')],check=True)
with tarfile.open(P/'results.tar.gz') as t:
 for p in t.getmembers():assert p.isfile() and '/' not in p.name and '\\' not in p.name
 t.extractall(O,filter='data')
