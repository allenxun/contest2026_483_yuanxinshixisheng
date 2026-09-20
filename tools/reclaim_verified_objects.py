"""Reclaim only redundant .o files of explicitly archived old SDK builds."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R/'evidence/build-space-20260910'
E.mkdir(exist_ok=True)
p = argparse.ArgumentParser()
p.add_argument('--apply', action='store_true')
a = p.parse_args()
revisions = ['emmc-readonly-20260910','emmc-gpt-20260910','emmc-block-20260910',
             'emmc-vfs-20260910','smp-diag-20260910','smp-reset-20260910',
             'smp-four-20260910','smp-eight-20260910']
expected = {}
for rev in revisions:
    report = json.loads((R/'evidence/build'/rev/'verification.json').read_text())
    assert report['build_exit_code'] == 0
    for name, item in report['artifacts'].items():
        data = (R/'artifacts'/rev/name).read_bytes()
        assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']
    expected['velavision_'+rev.replace('-20260910','_20260910').replace('-','_')] = report['artifacts']
script = '''import hashlib,json,os,shutil,stat
from pathlib import Path
ROOT=Path('/home/swl/openvela/cmake_out').resolve()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
'''
script += 'EXPECTED='+repr(expected)+'\n'
script += '''
for name,items in EXPECTED.items():
 b=ROOT/name
 assert b.resolve().parent==ROOT and not b.is_symlink()
 for rel,item in items.items():
  p=b/rel
  assert p.is_file() and not p.is_symlink() and sha(p)==item['sha256'],str(p)
'''
if a.apply:
    plan = json.loads((E/'plan.json').read_text())
    assert plan['directories'] == sorted(expected)
    script += 'FILES='+repr(plan['files'])+'\n'
    script += '''
for x in FILES:
 p=Path(x['path']);resolved=p.resolve()
 assert p.suffix=='.o' and not p.is_symlink() and resolved.is_relative_to(ROOT)
 assert resolved.relative_to(ROOT).parts[0] in EXPECTED
 assert stat.S_ISREG(p.stat().st_mode) and p.stat().st_size==x['bytes'] and sha(p)==x['sha256']
for x in FILES: Path(x['path']).unlink()
for name,items in EXPECTED.items():
 for rel,item in items.items(): assert sha(ROOT/name/rel)==item['sha256']
print(json.dumps(dict(removed_objects=len(FILES),removed_bytes=sum(x['bytes'] for x in FILES),
                     preserved_final_artifacts=True,free_bytes=shutil.disk_usage(ROOT).free)))
'''
else:
    script += '''
files=[]
for name in EXPECTED:
 for p in sorted((ROOT/name).rglob('*.o')):
  resolved=p.resolve()
  if p.is_symlink() or not stat.S_ISREG(p.stat().st_mode): continue
  assert resolved.is_relative_to(ROOT/name)
  files.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
print(json.dumps(dict(directories=sorted(EXPECTED),files=files,
                     reclaim_bytes=sum(x['bytes'] for x in files),preserve='ELF, bin, config, archives, sources, logs')))
'''
opts = ['-i',r'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519',
        '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8',
        '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
result = subprocess.run(['ssh.exe',*opts,'swl@192.168.152.131','python3 -'],input=script,
    text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
assert result.returncode == 0, result.stderr
value = json.loads(result.stdout)
with (E/('applied.json' if a.apply else 'plan.json')).open('x') as f: json.dump(value,f,indent=2)
print(json.dumps({k:v for k,v in value.items() if k!='files'}))
