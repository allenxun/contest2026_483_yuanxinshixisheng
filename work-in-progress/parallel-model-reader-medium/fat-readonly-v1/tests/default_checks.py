# Executed in run_tests globals, shares exact extractor and command recorder.
default_main='''int main(void){struct inode block={0};struct fat_mountpt_s fs={0};uint8_t temp[512];block.u.i_bops=&ops;fs.fs_blkdriver=&block;
CHECK(fat_mount(&fs,true)==-EACCES && reads==0);geo_writable=1;CHECK(fat_mount(&fs,true)==0);
CHECK(fat_hwwrite(&fs,temp,0,1)==0 && writes==1);fat_io_free(fs.fs_buffer,512);CHECK(allocs==frees);
printf("PASS default geometry rejection / writable mount / real write dispatch writes=%u\\n",writes);return 0;}'''
for folder,tag in [('input/fat','original'),('candidate/fat','candidate')]:
 source='#include "compat.h"\n'+''.join(extract(folder,'fs_fat32util.c',n) for n in ['fat_hwread','fat_hwwrite','fat_mount'])+default_main
 (R/'tests'/('default_'+tag+'.c')).write_text(source)
 run([CC,'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter','-Wno-sign-compare','tests/default_'+tag+'.c','-o','evidence/default_'+tag+'.exe'],30)
 run([R/'evidence'/('default_'+tag+'.exe')])
# Strip includes only for preprocessing equivalence: does not compile full FAT.
# Compare ALL original/candidate C tokens with new option disabled, in two
# feature sets including LFN + UTF8 + COMPUTE_FSINFO + LARGEFILE.
for features in [[],['-DCONFIG_FAT_LFN','-DCONFIG_FAT_LFN_UTF8','-DCONFIG_FAT_COMPUTE_FSINFO','-DCONFIG_FS_LARGEFILE']]:
 for name in ['fs_fat32.c','fs_fat32util.c','fs_fat32dirent.c','fs_fat32attrib.c']:
  outputs=[]
  for folder,tag in [('input/fat','original'),('candidate/fat','candidate')]:
   source=re.sub(r'^\s*#\s*include[^\n]*','',(R/folder/name).read_text(),flags=re.M)
   path=R/'tests'/(tag+'-preprocess.c');path.write_text(source)
   outputs.append(run([CC,'-E','-P',*features,str(path)]))
  assert re.sub(r'\s+','',outputs[0])==re.sub(r'\s+','',outputs[1]),name+' default tokens changed'
records.append({'check':'default-disabled all four C token streams equal in 2 feature sets; includes stripped, not full target compile','passed':True})
# Final RO sink audit; no invocation of write callback or timestamp encoder.
ro_text=[]
for file in ['fs_fat32.c','fs_fat32util.c','fs_fat32dirent.c','fs_fat32attrib.c']:
 text=re.sub(r'^\s*#\s*include[^\n]*','',(R/'candidate/fat'/file).read_text(),flags=re.M)
 path=R/'tests'/'readonly-preprocess.c';path.write_text(text)
 ro_text.append(run([CC,'-E','-P','-DCONFIG_FAT_FORCE_READONLY','-DCONFIG_FAT_COMPUTE_FSINFO','-DCONFIG_FAT_LFN',str(path)]))
joined='\n'.join(ro_text)
assert not re.search(r'->\s*write\s*\(',joined)
assert len(re.findall(r'\bfat_systime2fattime\s*\(',joined))==1 # definition only
assert not re.search(r'fs_fsidirty\s*=\s*true',joined)
records.append({'check':'RO preprocessed code has zero block write callback calls, zero timestamp encoder calls, zero FSInfo dirty=true assignments','passed':True})
