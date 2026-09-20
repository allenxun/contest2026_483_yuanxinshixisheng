import pathlib, re, json, subprocess, hashlib
R=pathlib.Path(__file__).resolve().parent
P=R.parents[2]
R.joinpath('evidence').mkdir(exist_ok=True)
paths=['evidence/usb-storage-inputs-20260910/nuttx/fs/fat/fs_fat32.c','evidence/usb-storage-inputs-20260910/nuttx/fs/fat/fs_fat32.h','evidence/usb-storage-inputs-20260910/nuttx/fs/fat/fs_fat32util.c','app/k7agent/model_reader/model_reader.c','app/k7agent/model_reader/model_reader.h','work-in-progress/parallel-neon-probe-medium/model-file-integration-v1/HANDOFF.md']
paths += [p.relative_to(P).as_posix() for p in (P/'evidence/model-file-vfs-inputs-20260910').rglob('*') if p.is_file()]
inputs=[{'path':p,'sha256':hashlib.sha256((P/p).read_bytes()).hexdigest()} for p in paths]
(R/'evidence/inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
def mask(s):
 return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',lambda m:' '*len(m.group()),s)
def function(s,name):
 clean=mask(s)
 m=re.search(r'(?m)^[ \t]*(?:static\s+)?(?:int|off_t)\s+'+name+r'\s*\([^;{}]*\)\s*\{',clean)
 assert m,name
 end=clean.find('{',m.start())+1; level=1
 while level:
  if clean[end]=='{':level+=1
  elif clean[end]=='}':level-=1
  end+=1
 return s[m.start():end]
s=(P/paths[0]).read_text()
names=['fat_stat_common','fat_stat_file','fat_fstat','fat_seek']
(R/'selected.c').write_text('#include "compat.h"\n'+'\n'.join(function(s,n) for n in names)+'\n'+(R/'test_body.c').read_text())
gcc=r'D:\software\mingw64\mingw64\bin\gcc.exe'
results=[]
for bits in [64,32]:
 for cmd,timeout in [([gcc,'-std=c11','-Wall','-Wextra','-Werror',f'-DOFF_BITS={bits}','selected.c','-o',f'evidence/contract{bits}.exe'],30),([str(R/f'evidence/contract{bits}.exe')],15)]:
  run=subprocess.run(cmd,cwd=R,capture_output=True,text=True,timeout=timeout)
  results.append({'command':cmd,'timeout_seconds':timeout,'returncode':run.returncode,'stdout':run.stdout,'stderr':run.stderr})
  (R/'evidence/results.json').write_text(json.dumps(results,indent=2)+'\n')
  print(run.stdout,run.stderr,end='')
  if run.returncode:raise SystemExit(run.returncode)
