"""Resume the exact staged build after space recovery, without rewriting inputs."""
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
S = R/'private/fat-readonly-20260910'
E = R/'evidence/build/fat-readonly-20260910'/('resume-input-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
E.mkdir(parents=True, exist_ok=True)
assert not (E.parent/'verification.json').exists()
opts = ['-i',r'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519',
        '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8',
        '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host = 'swl@192.168.152.131'
remote_dir = '/home/swl/openvela/work/velavision-fat-readonly-20260910'
for name in ('build.log','sync-check.log'):
    target = E/name
    assert not target.exists()
    subprocess.run(['scp.exe',*opts,host+':'+remote_dir+'/'+name,str(target)],check=True)
(E/'staging.json').write_bytes((S/'staging.json').read_bytes())
code = (S/'build.py').read_text()
code = code.replace("sha(p) not in {v['new'],v['old']}", "sha(p) != v['new']")
copy = "for rel in m:\n p=P/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((S/rel).read_bytes())"
assert copy in code
code = code.replace(copy, "assert not (O/'verification.json').exists(), 'Completed build is immutable'")
old = "build=run('build',['bash',str(P/'tools/build_fat_readonly.sh'),str(SDK)])"
assert old in code
code = code.replace(old, "import os\ntmp=Path('/dev/shm/velavision-fat-compiler');tmp.mkdir(exist_ok=True)\nos.environ['TMPDIR']=str(tmp)\ncompiler=SDK/'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin'\nassert (compiler/'aarch64-none-elf-ar').is_file()\nos.environ['PATH']=str(compiler)+os.pathsep+os.environ['PATH']\nbuild=run('build',['cmake','--build',str(SDK/'cmake_out/velavision_fat_readonly_20260910'),'-j4'])")
(S/'resume-build.py').write_text(code, newline='\n')
subprocess.run(['ssh.exe',*opts,host,'python3 -'],input=code,text=True,check=True)
result = S/'result.tar.gz'
subprocess.run(['scp.exe',*opts,host+':'+remote_dir+'/result.tar.gz',str(result)],check=True)
with tarfile.open(result) as t:
    for member in t.getmembers():
        assert (R/member.name).resolve().is_relative_to(R) and member.isfile()
    t.extractall(R, filter='data')
print('Incremental FAT build and original failure evidence saved')
