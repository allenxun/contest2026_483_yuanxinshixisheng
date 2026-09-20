import pathlib,subprocess,hashlib,json
p=pathlib.Path(__file__).resolve().parent
root=p.parents[2]
names=['port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c',
 'port/new/nuttx/arch/arm64/src/rk3576/hardware/rk3576_memorymap.h',
 'work-in-progress/parallel-cxx-unwind-medium/audio-rx-machine-review-v1/REVIEW.md',
 'work-in-progress/parallel-cxx-unwind-medium/audio-rx-machine-review-v1/symbols.txt',
 'work-in-progress/parallel-cxx-unwind-medium/audio-rx-machine-review-v1/frozen-.config',
 'work-in-progress/parallel-cxx-unwind-medium/audio-rx-machine-review-v1/elf-layout.json',
 'work-in-progress/parallel-cxx-unwind-medium/audio-rx-machine-review-v1/source-binding.json']
items=[]
names += ['evidence/audio-mmu-input-20260910/'+n for n in
 ['inputs.json','arm64_mmu.c','arm64_mmu.h','arm64_arch.h','rk3576_boot.c','config','elf-table-symbols.json']]
for n in names:
 b=(root/n).read_bytes();d=p/'input'/n;d.parent.mkdir(parents=True,exist_ok=True)
 if d.exists():assert d.read_bytes()==b
 else:d.write_bytes(b)
 items.append(dict(path=n,sha256=hashlib.sha256(b).hexdigest()))
(p/'inputs.json').write_text(json.dumps(items,indent=2))
runs=[]
for opt in ('O0','O2'):
 cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-'+opt,'mmu_probe.c','snapshot_arm64.c','test.c','-o','test-'+opt+'.exe']
 c=subprocess.run(cmd,cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('compile-'+opt+'.txt')).write_bytes(c.stdout);assert c.returncode==0,c.stdout
 t=subprocess.run([str(p/('test-'+opt+'.exe'))],cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('test-'+opt+'.txt')).write_bytes(t.stdout);assert t.returncode==0,t.stdout
 runs.append(dict(command=cmd,compile_rc=c.returncode,test_rc=t.returncode))
(p/'runs.json').write_text(json.dumps(runs,indent=2))
print('PASS O0/O2 bounded MMU walker tests')
