import pathlib,hashlib,json,difflib,subprocess
ROOT=pathlib.Path(__file__).resolve().parent
PROJECT=ROOT.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
original=(ROOT/'input/k7storage_main.c').read_text(encoding='utf-8')
start=original.index('  while ((entry = readdir(dir)) != NULL)')
end=original.index('\n  printf("USB_STORAGE nodes=',start)
replacement='''  int rc = 0;
  unsigned visited = 0;
  for (;;)
    {
      /* Conservative bound: reaching 256 entries fails, even if EOF is next. */
      if (visited == 256) { rc = -E2BIG; break; }
      errno = 0;
      entry = readdir(dir);
      if (!entry) { if (errno) rc = -errno; break; }
      ++visited;
      if (strlen(entry->d_name) == 3 && entry->d_name[0] == 's' &&
          entry->d_name[1] == 'd' && entry->d_name[2] >= 'a' &&
          entry->d_name[2] <= 'z')
        {
          printf("USB_STORAGE node=/dev/%s\\n", entry->d_name);
          ++count;
        }
    }
  if (closedir(dir) < 0 && rc == 0) rc = errno ? -errno : -EIO;'''
candidate=original[:start]+replacement+original[end:]
anchor='  printf("USB_STORAGE nodes=%u\\n", count);\n  return 0;'
assert candidate.count(anchor)==1
candidate=candidate.replace(anchor,'  printf("USB_STORAGE nodes=%u\\n", count);\n  return rc;')
(ROOT/'candidate.c').write_text(candidate,encoding='utf-8')
(ROOT/'list-errors.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),'a/app/k7storage/k7storage_main.c','b/app/k7storage/k7storage_main.c')),encoding='utf-8')
inputs={p.relative_to(PROJECT).as_posix():sha(p) for p in (PROJECT/'app/k7storage').iterdir() if p.is_file()}
for p in (ROOT/'input').iterdir():
 assert sha(p)==inputs['app/k7storage/'+p.name], 'formal source changed after freeze'
for name in ['evidence/usb-storage-inputs-20260910/nuttx/include/nuttx/fs/fs.h','evidence/usb-storage-inputs-20260910/nuttx/include/sys/mount.h','evidence/usb-storage-vfs-20260910/nuttx/include/fcntl.h','evidence/storage-types-inputs-20260910/nuttx/include/nuttx/fs/ioctl.h','evidence/storage-types-inputs-20260910/nuttx/include/nuttx/fs/fs.h','evidence/model-file-vfs-inputs-20260910/nuttx/include/sys/types.h']:
 inputs[name]=sha(PROJECT/name)
(ROOT/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
results=[]
for name,defs in [('original',[]),('candidate',['-DFIXED'])]:
 for command in [['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Imock',*defs,'test_storage.c','-o',name+'.exe'],[str(ROOT/(name+'.exe'))]]:
  p=subprocess.run(command,cwd=str(ROOT),timeout=15,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  i=len(results);(ROOT/(str(i)+'.stdout')).write_bytes(p.stdout);(ROOT/(str(i)+'.stderr')).write_bytes(p.stderr)
  results.append(dict(command=command,returncode=p.returncode,stdout=p.stdout.decode('utf-8','replace'),stderr=p.stderr.decode('utf-8','replace')))
  if p.returncode:break
 if results[-1]['returncode']:break
(ROOT/'host-results.json').write_text(json.dumps(dict(scope='real app source with mock APIs; geometry shape not target verified',passed=len(results)==4 and all(r['returncode']==0 for r in results),results=results),indent=2)+'\n',encoding='utf-8')
(ROOT/'hashes.json').write_text(json.dumps({str(p.relative_to(ROOT)):sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name!='hashes.json'},indent=2)+'\n',encoding='utf-8')
print(json.dumps([dict(command=r['command'],returncode=r['returncode'],stderr=r['stderr']) for r in results],indent=2))
raise SystemExit(0 if len(results)==4 and all(r['returncode']==0 for r in results) else 1)
