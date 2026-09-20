import pathlib,re,json,subprocess,os,time
R=pathlib.Path(__file__).resolve().parent
# Import only extractor definitions (do not rerun candidate mutation).
namespace={};exec((R/'prepare_candidate.py').read_text().split('MODS={}')[0],{'__file__':str(R/'prepare_candidate.py')},namespace)
# Functions refer to globals: supply the mask dependency explicitly.
span=namespace['span'];span.__globals__['mask']=namespace['mask'];span.__globals__['re']=re
CC=pathlib.Path(r'D:\software\mingw64\mingw64\bin\gcc.exe');env=dict(os.environ);env['PATH']=str(CC.parent)+os.pathsep+env['PATH'];records=[]
def run(args,t=15):
 p=subprocess.run([str(x) for x in args],cwd=R,env=env,capture_output=True,text=True,timeout=t)
 records.append({'command':[str(x) for x in args],'timeout_seconds':t,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
def extract(folder,file,name):
 s=(R/folder/file).read_text();a,b,e=span(s,name);return s[a:e]+'\n'
try:
 run([CC,'--version'])
 funcs=['fat_hwread','fat_hwwrite','fat_mount','fat_checkmount','fat_fscacheflush','fat_ffcacheflush','fat_fscacheread','fat_ffcacheread','fat_ffcacheinvalidate','fat_updatefsinfo','fat_computefreeclusters']
 generated='#include "compat.h"\n'+''.join(extract('candidate/fat','fs_fat32util.c',n) for n in funcs)
 generated+=''.join(extract('candidate/fat','fs_fat32.c',n) for n in ['fat_sync','fat_read','fat_close','fat_bind','fat_unbind'])
 guards=json.loads((R/'evidence/guarded-functions.json').read_text());calls=[]
 for name in guards:
  if name in funcs or name=='fat_sync':continue
  for f in (R/'candidate/fat').glob('*.c'):
   try:a,b,e=span(f.read_text(),name)
   except AssertionError:continue
   text=f.read_text()[a:e];generated+=text+'\n'
   sig=text[:text.index('{')];params=sig[sig.index('(')+1:sig.rfind(')')]
   calls.append('CHECK('+name+'('+','.join('0' for p in params.split(','))+')==-EROFS);');break
 # Test exact inserted open policy fragment, not the uncompiled full fat_open body.
 op=extract('candidate/fat','fs_fat32.c','fat_open');policy=op[op.index('#ifdef'):op.index('#endif')+len('#endif')]
 generated+='static int open_policy_fragment(int oflags){\n'+policy+'\nreturn 0;}\n'
 generated+='''int main(void){
 struct inode block={0},mount={0},*returned=NULL;struct fat_mountpt_s *fs;struct fat_file_s *ff;struct file file;void *handle=NULL;uint8_t tmp[512];
 block.u.i_bops=&ops;CHECK(fat_bind(&block,NULL,&handle)==0 && handle);fs=handle;mount.i_private=fs;
 CHECK(fs->fs_mounted && reads>0 && writes==0);
 CHECK(fat_computefreeclusters(fs)==0 && fs->fs_fsifreecount==4 && !fs->fs_fsidirty);
 CHECK(fat_hwread(fs,tmp,3,1)==0 && tmp[0]==3);
 short_read=1;CHECK(fat_hwread(fs,tmp,3,1)<0);short_read=0;read_error=1;CHECK(fat_hwread(fs,tmp,3,1)==-EIO);read_error=0;
 CHECK(fat_hwwrite(fs,tmp,0,1)==-EROFS && writes==0);
 CHECK(fat_fscacheread(fs,4)==0 && fs->fs_buffer[0]==4);
 fs->fs_dirty=true;CHECK(fat_fscacheread(fs,5)==-EROFS && fs->fs_dirty);fs->fs_dirty=false;
 ff=fs_heap_zalloc(sizeof(*ff));ff->ff_buffer=fat_io_alloc(512);fs->fs_head=ff;file=(struct file){&mount,ff,0};
 ff->ff_size=1024;ff->ff_oflags=O_RDONLY;file.f_pos=510;CHECK(fat_read(&file,(char*)tmp,4)==4 && tmp[0]==8 && tmp[1]==8 && tmp[2]==9 && tmp[3]==9);
 file.f_pos=0;CHECK(fat_read(&file,(char*)tmp,512)==512 && tmp[0]==8);file.f_pos=1024;CHECK(fat_read(&file,(char*)tmp,1)==0);
 CHECK(fat_ffcacheread(fs,ff,6)==0 && ff->ff_buffer[0]==6);
 CHECK(fat_ffcacheinvalidate(fs,ff)==0);
 CHECK(fat_sync(&file)==0 && writes==0);
 ff->ff_bflags|=FFBUFF_MODIFIED;CHECK(fat_sync(&file)==-EROFS && (ff->ff_bflags&FFBUFF_MODIFIED));ff->ff_bflags=0;
 fs->fs_fsidirty=true;CHECK(fat_updatefsinfo(fs)==-EROFS && fs->fs_fsidirty);fs->fs_fsidirty=false;
 CHECK(fat_updatefsinfo(fs)==0);
 CHECK(open_policy_fragment(O_RDONLY)==0);CHECK(open_policy_fragment(O_WRONLY)==-EROFS);CHECK(open_policy_fragment(O_RDWR)==-EROFS);
 CHECK(open_policy_fragment(O_RDONLY|O_CREAT)==-EROFS);CHECK(open_policy_fragment(O_RDONLY|O_TRUNC)==-EROFS);CHECK(open_policy_fragment(O_RDONLY|O_APPEND)==-EROFS);CHECK(open_policy_fragment(O_RDONLY|O_EXCL)==-EROFS);
 '''+'\n'.join(calls)+'''
 CHECK(fat_close(&file)==0 && !file.f_priv && !fs->fs_head);
 CHECK(fat_unbind(handle,&returned,0)==0 && returned==&block && opens==1 && closes==1);
 CHECK(writes==0 && allocs==frees);
 printf("PASS selected real FAT C branches: mount/read/cache/sync/close/unbind/mutator guards; reads=%u writes=%u allocs=%u frees=%u; boot+FSInfo validators mocked\\n",reads,writes,allocs,frees);return 0;}
'''
 (R/'tests/selected_ro.c').write_text(generated)
 run([CC,'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter','-Wno-sign-compare','-DCONFIG_FAT_FORCE_READONLY','tests/selected_ro.c','-o','evidence/selected_ro.exe'],30)
 run([R/'evidence/selected_ro.exe'])
 run([CC,'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter','-Wno-sign-compare','-DCONFIG_FAT_FORCE_READONLY','-DCONFIG_FAT_FORCE_INDIRECT','-DCONFIG_FAT_COMPUTE_FSINFO','tests/selected_ro.c','-o','evidence/selected_indirect.exe'],30)
 run([R/'evidence/selected_indirect.exe'])
 exec((R/'tests/default_checks.py').read_text())
finally:(R/'evidence/host-tests.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'extracted actual functions + explicit host mocks; not whole FAT/target build','results':records},indent=2),encoding='utf-8')


