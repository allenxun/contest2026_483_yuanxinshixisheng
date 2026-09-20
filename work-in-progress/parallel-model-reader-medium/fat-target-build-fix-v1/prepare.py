import pathlib,re,difflib,hashlib,json,subprocess
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
src=P/'port/tracked/nuttx/fs/fat/fs_fat32dirent.c'
raw=src.read_bytes();s=raw.decode();s=s.replace('\r\n','\n')
(R/'input.c').write_bytes(raw)
names=['fat_createalias','fat_findalias','fat_uniquealias','fat_allocatesfnentry','fat_allocatelfnentry','fat_putsfname','fat_initlfname','fat_putlfnchunk','fat_putlfname','fat_putsfdirentry']
def mask(s):return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',lambda m:' '*len(m.group()),s)
edits=[];clean=mask(s)
for name in names:
 matches=list(re.finditer(r'(?m)^static\s+(?:inline\s+)?(?:int|void)\s+'+name+r'\s*\([^;{}]*\)\s*([;{])',clean))
 assert len(matches)==2,(name,len(matches))
 for m in matches:
  end=m.end()
  if m.group(1)=='{':
   level=1
   while level:
    level+=(clean[end]=='{')-(clean[end]=='}');end+=1
  edits.append((m.start(),end))
candidate=s
for start,end in sorted(edits,reverse=True):
 candidate=candidate[:start]+'#ifndef CONFIG_FAT_FORCE_READONLY\n'+candidate[start:end]+'\n#endif /* !CONFIG_FAT_FORCE_READONLY */'+candidate[end:]
(R/'fs_fat32dirent.c').write_text(candidate,encoding='utf-8')
(R/'fix.patch').write_text(''.join(difflib.unified_diff(s.splitlines(True),candidate.splitlines(True),fromfile='a/fs/fat/fs_fat32dirent.c',tofile='b/fs/fat/fs_fat32dirent.c')),encoding='utf-8')
results=[];gcc=r'D:\software\mingw64\mingw64\bin\gcc.exe'
for features in [[],['CONFIG_FAT_LFN'],['CONFIG_FAT_LFN','CONFIG_FAT_LFN_UTF8','CONFIG_FAT_LCNAMES','CONFIG_FAT_LFN_ALIAS_HASH']]:
 texts={}
 for ro in [False,True]:
  for label,code in [('input',s),('candidate',candidate)]:
   path=R/'preprocess.c';path.write_text(re.sub(r'^\s*#\s*include[^\n]*','',code,flags=re.M))
   cmd=[gcc,'-E','-P']+['-D'+f for f in features]+(['-DCONFIG_FAT_FORCE_READONLY'] if ro else [])+[str(path)]
   run=subprocess.run(cmd,capture_output=True,text=True,timeout=15);assert run.returncode==0,run.stderr
   texts[label,ro]=run.stdout
  if not ro:assert re.sub(r'\s','',texts['input',False])==re.sub(r'\s','',texts['candidate',False])
  else:
   for n in names:assert not re.search(r'\b'+n+r'\s*\(',texts['candidate',True]),n
   for n in ['fat_parsesfname','fat_findsfnentry','fat_getsfname']:assert n in texts['candidate',True]
   if 'CONFIG_FAT_LFN' in features:
    for n in ['fat_lfnchecksum','fat_parselfname','fat_cmplfname','fat_findlfnentry','fat_getlfname']:assert n in texts['candidate',True]
 results.append({'features':features,'default_token_equivalence':True,'readonly_removed_all_ten_helpers_and_declarations':True,'read_helpers_retained':True})
(R/'checks.json').write_text(json.dumps({'input_path':str(src),'input_sha256':hashlib.sha256(raw).hexdigest(),'candidate_sha256':hashlib.sha256((R/'fs_fat32dirent.c').read_bytes()).hexdigest(),'guarded_functions':names,'scope':'Preprocessor/call-site audit only; complete target compilation remains root work','checks':results},indent=2)+'\n')
print((R/'checks.json').read_text())
