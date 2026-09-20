import pathlib, subprocess, hashlib, json, shutil
R=pathlib.Path(__file__).resolve().parent
P=R.parents[2]
paths=list((P/'app/k7storage').glob('*'))
B=P/'work-in-progress/parallel-model-reader-medium/fat-readonly-v1'
paths += list((B/'candidate/fat').glob('*'))+[B/'HANDOFF.md',B/'delivery.json']
paths += [P/s for s in ['evidence/usb-storage-inputs-20260910/nuttx/include/sys/mount.h','evidence/usb-storage-mount-20260910/nuttx/fs/mount/fs_mount.c','evidence/usb-storage-mount-20260910/nuttx/fs/mount/fs_umount2.c','port/tracked/nuttx/drivers/usbhost/usbhost_storage.c']]
manifest=[]
for i,p in enumerate(paths):
 if not p.is_file(): continue
 data=p.read_bytes(); dest=R/'input'/('%02d_'%i+p.name); dest.write_bytes(data)
 manifest.append({'source':str(p.relative_to(P)),'snapshot':dest.name,'sha256':hashlib.sha256(data).hexdigest()})
(R/'inputs.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
commands=[[shutil.which('gcc'),'-std=c11','-Wall','-Wextra','-Werror','-pedantic','-Imock','test.c','-o','test.exe'],[str(R/'test.exe')]]
with (R/'test-output.txt').open('wb') as f:
 for cmd in commands:
  f.write(('COMMAND '+repr(cmd)+'\n').encode())
  p=subprocess.run(cmd,cwd=str(R),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
  f.write(p.stdout);f.write(('EXIT %d\n'%p.returncode).encode())
  if p.returncode: raise SystemExit(p.returncode)
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
print('PASS compile and test; see test-output.txt')
