"""Compile only the reviewed ORT Env translation unit with real NuttX flags.
No link, model, SDK edit or board action. All scratch output is in VM tmpfs.
"""
import hashlib,json,shlex,subprocess,tarfile,zipfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
B=R/'work-in-progress/native-voice-sources'
O=R/'evidence/native-ort-env-compile3-20260911';O.mkdir(exist_ok=True)
P=R/'private/native-ort-env-stage';P.mkdir(exist_ok=True)
C=R/'work-in-progress/parallel-model-reader-medium/env-gate-v2'
assert hashlib.sha256((C/'outputs.json').read_bytes()).hexdigest()=='84e266c17d1ee61b15f07697e53be28cd33f6a46daa706f985b6fd6b97028fca'
for row in json.loads((C/'outputs.json').read_text()):
    assert hashlib.sha256((C/row['path']).read_bytes()).hexdigest()==row['sha256']
source=B/'onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d'
archive=P/'input.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for base in ('include/onnxruntime','onnxruntime/core/common','onnxruntime/core/platform','onnxruntime/core/framework'):
        for p in (source/base).rglob('*.h'):
            tar.add(p,arcname='ort/'+p.relative_to(source).as_posix())
    tar.add(C/'env-gate.cc',arcname='env-gate.cc')
    eigen=R/'work-in-progress/parallel-model-reader-medium/eigen-source-check-v1-export'
    assert hashlib.sha256((eigen/'source-manifest.json').read_bytes()).hexdigest()=='6c963166563af7f1cfec1341642ca7e045f0ab11083416f7511a7c973c8c0ae6'
    for rel,item in json.loads((eigen/'source-manifest.json').read_text()).items():
        p=eigen/'source'/rel
        assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
        info=tar.gettarinfo(p,arcname='eigen/'+rel);info.mode=int(item['git_mode'],8)&0o777
        with p.open('rb') as stream:tar.addfile(info,stream)
    # Original template contains only warning-feature flags and version strings.
    # Leave unprobed flags undefined for this translation-unit gate; no runtime
    # capability or full upstream CMake configuration is fabricated.
    template=(source/'cmake/onnxruntime_config.h.in').read_text()
    assert all(not line.startswith('#cmakedefine') or line.split()[1].startswith(('HAS_','ORT_BUILD_INFO','ORT_VERSION')) for line in template.splitlines())
    header='\n'.join('/* '+line+' intentionally unset in isolated compile gate */' if line.startswith('#cmakedefine') else line for line in template.splitlines())
    (P/'onnxruntime_config.h').write_text(header)
    tar.add(P/'onnxruntime_config.h',arcname='onnxruntime_config.h')
for name in ('abseil_cpp','microsoft_gsl','safeint','google_nsync'):
    z=B/'deps'/(name+'.zip');meta=json.loads(z.with_suffix('.json').read_text())
    assert hashlib.sha256(z.read_bytes()).hexdigest()==meta['sha256']
    # Stage only files within the verified archive under a fresh private tree.
    out=P/name
    if not out.exists():
        out.mkdir()
        with zipfile.ZipFile(z) as package:
            for member in package.infolist():
                rel=Path(*member.filename.split('/')[1:])
                assert not rel.is_absolute() and '..' not in rel.parts
                if member.is_dir():continue
                target=out/rel;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(package.read(member))
# Repack once to include verified dependency inputs and exact compile driver.
remote=r'''
import json,shlex,subprocess,hashlib
from pathlib import Path
S=Path('/dev/shm/velavision-ort-env3-20260911')
B=Path('/dev/shm/velavision_audio_sound_20260910')
entries=json.loads((B/'compile_commands.json').read_text())
entry=next(x for x in entries if x['file'].endswith('/k7voice_main.cpp'))
args=entry.get('arguments') or shlex.split(entry['command'])
result=[];i=0
while i<len(args):
 a=args[i]
 if a in ('-o','-MF','-MT','-MQ'):i+=2;continue
 if a in ('-MD','-MMD','-c') or a==entry['file'] or a.startswith('-Dmain='):i+=1;continue
 result.append(a);i+=1
result += ['-DORT_K7_NUTTX=1','-DNSYNC_ATOMIC_CPP11','-std=c++17','-I'+str(S/'ort/include/onnxruntime'),'-I'+str(S/'ort/onnxruntime'),
 '-I'+str(S),'-I'+str(S/'eigen'),'-I'+str(S/'abseil_cpp'),'-I'+str(S/'microsoft_gsl/include'),'-I'+str(S/'safeint'),
 '-I'+str(S/'google_nsync/public'),'-c',str(S/'env-gate.cc'),'-o',str(S/'env-gate.o')]
(S/'command.json').write_text(json.dumps(result,indent=2))
p=subprocess.run(result,cwd=entry['directory'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
(S/'compile.log').write_bytes(p.stdout)
(S/'result.json').write_text(json.dumps(dict(exit_code=p.returncode,linked=False,hardware_tested=False,
 scope='single ORT Env translation unit using actual NuttX compile flags',
 config_sha256=hashlib.sha256((B/'.config').read_bytes()).hexdigest()),indent=2))
print('ORT_ENV_COMPILE',p.returncode,flush=True)
print(p.stdout.decode(errors='replace')[-6000:],flush=True)
'''
(P/'compile.py').write_text(remote)
with tarfile.open(P/'stage.tar.gz','w:gz') as tar:
    tar.add(archive,arcname='input.tar.gz');tar.add(P/'compile.py',arcname='compile.py')
    for name in ('abseil_cpp','microsoft_gsl','safeint','google_nsync'):tar.add(P/name,arcname=name)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-env3-20260911'
def call(args):subprocess.run(args,check=True)
call(['ssh.exe',*options,host,'mkdir '+dest])
call(['scp.exe',*options,str(P/'stage.tar.gz'),host+':'+dest+'/stage.tar.gz'])
call(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && tar -xzf input.tar.gz && python3 compile.py'])
for name in ('command.json','compile.log','result.json'):
    call(['scp.exe',*options,host+':'+dest+'/'+name,str(O/name)])
