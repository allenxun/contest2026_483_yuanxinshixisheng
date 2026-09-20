import pathlib,subprocess,hashlib,json,difflib
p=pathlib.Path(__file__).resolve().parent;root=p.parents[2]
names=['app/k7sound/k7sound_main.c','app/k7sound/i2c_owner.inc','app/k7load/k7load_main.c']
names+=['work-in-progress/parallel-neon-probe-medium/audio-mmu-runtime-v1/'+n for n in ['mmu_probe.c','mmu_probe.h','snapshot_arm64.c']]
names+=['evidence/audio-mmu-input-20260910/'+n for n in ['inputs.json','arm64_mmu.c','arm64_mmu.h','arm64_arch.h','config','rk3576_boot.c','elf-table-symbols.json']]
items=[]
for n in names:
 b=(root/n).read_bytes();f=p/'input'/n;f.parent.mkdir(parents=True,exist_ok=True)
 if f.exists():assert f.read_bytes()==b,'Frozen source changed'
 else:f.write_bytes(b)
 items.append(dict(path=n,sha256=hashlib.sha256(b).hexdigest()))
(p/'inputs.json').write_text(json.dumps(items,indent=2))
old=(p/'input/app/k7sound/k7sound_main.c').read_text()
new=old.replace('#include "duplex.h"','#include "duplex.h"\n#include "mmu_command.h"',1)
new=new.replace('int main(int argc, char **argv)\n{','int main(int argc, char **argv)\n{\n  if (argc > 1 && !strcmp(argv[1], "mmu"))\n    return k7sound_mmu_command(argc, argv, &owner);',1)
(p/'main-integration.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/app/k7sound/k7sound_main.c',tofile='b/app/k7sound/k7sound_main.c')))
runs=[]
for opt in ('O0','O2'):
 cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-'+opt,'command_core.c','mmu_probe.c','test.c','-o','test-'+opt+'.exe']
 a=subprocess.run(cmd,cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('compile-'+opt+'.txt')).write_bytes(a.stdout);assert a.returncode==0,a.stdout
 b=subprocess.run([str(p/('test-'+opt+'.exe'))],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('test-'+opt+'.txt')).write_bytes(b.stdout);assert b.returncode==0,b.stdout
 runs.append(dict(command=cmd,compile_rc=a.returncode,test_rc=b.returncode))
(p/'runs.json').write_text(json.dumps(runs,indent=2))
print('PASS O0/O2 command parameter and guarded execution tests')
