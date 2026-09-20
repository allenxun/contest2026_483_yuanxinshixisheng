import pathlib,subprocess,json,hashlib,difflib
r=pathlib.Path(__file__).resolve().parent
results=[]
for opt in ['-O0','-O2']:
 for name in ['duplex','max']:
  exe='test_'+name+opt+'.exe'
  commands=[([r'D:/software/mingw64/mingw64/bin/gcc.exe','-std=c11',opt,'-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-pedantic','codec_duplex.c','test_'+name+'.c','-o',exe],30),([str(r/exe)],15)]
  for cmd,limit in commands:
   p=subprocess.run(cmd,cwd=r,capture_output=True,text=True,timeout=limit)
   results.append(dict(command=cmd,timeout_seconds=limit,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
   (r/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
   print(p.stdout,p.stderr,end='')
   if p.returncode:raise SystemExit(p.returncode)
patch=''
for name in ['codec_duplex.c','codec_duplex.h']:
 patch+=''.join(difflib.unified_diff((r/('input-'+name)).read_text().splitlines(True),(r/name).read_text().splitlines(True),fromfile='a/app/k7sound/'+name,tofile='b/app/k7sound/'+name))
(r/'maxvolume.patch').write_text(patch,encoding='utf-8')
root=r.parents[2]
sources=['work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/codecs/es8323.c','work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/codecs/es8323.h','work-in-progress/parallel-model-reader-medium/audio-codec-datasheet-v1/guide-text.txt','work-in-progress/parallel-model-reader-medium/audio-playback-gain-v1/delivery.json']
(r/'inputs.json').write_text(json.dumps([dict(path=s,sha256=hashlib.sha256((root/s).read_bytes()).hexdigest()) for s in sources],indent=2),encoding='utf-8')
rows=[dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(r.iterdir()) if p.is_file() and p.name!='delivery.json']
(r/'delivery.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print('delivery sha256='+hashlib.sha256((r/'delivery.json').read_bytes()).hexdigest())
