import difflib
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=ROOT/'work-in-progress/parallel-model-reader-medium/fat-readonly-v1/candidate/fat'
def extract(text,name):
 import re
 for m in re.finditer(r'\b'+name+r'\s*\(',text):
  i=m.end();depth=1
  while depth:
   if text[i]=='(':depth+=1
   if text[i]==')':depth-=1
   i+=1
  while text[i].isspace():i+=1
  if text[i]!='{':continue
  a=i;i+=1;depth=1
  while depth:
   if text[i]=='{':depth+=1
   if text[i]=='}':depth-=1
   i+=1
  return a,i
 raise ValueError(name)
def prepare():
 old=(BASE/'fs_fat32.c').read_text(encoding='utf-8');a,b=extract(old,'fat_bind');body=old[a:b]
 body=body.replace('  int ret;','  int ret;\n  bool opened = false;',1)
 body=body.replace('  /* Create an instance', '  opened = blkdriver->u.i_bops->open != NULL;\n\n  /* Create an instance',1)
 body=body.replace('      return -ENOMEM;','      ret = -ENOMEM;\n      goto errout_with_open;',1)
 body=body.replace('      return ret;','      goto errout_with_open;',1)
 body=body.replace('  return OK;\n}', '''  return OK;

errout_with_open:
  /* VFS drops its inode reference on bind failure; only FAT owns this
   * successful block open. Preserve the primary failure if close fails. */

  if (opened && blkdriver->u.i_bops->close)
    {
      blkdriver->u.i_bops->close(blkdriver);
    }

  return ret;
}''')
 new=old[:a]+body+old[b:]
 (HERE/'candidate').mkdir(exist_ok=True)
 (HERE/'candidate/fs_fat32.c').write_text(new,encoding='utf-8')
 (HERE/'cleanup.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/fs/fat/fs_fat32.c',tofile='b/fs/fat/fs_fat32.c')),encoding='utf-8')
 for name in ('fs_fat32.c','fs_fat32util.c'):
  (HERE/('input-'+name)).write_bytes((BASE/name).read_bytes())
if __name__=='__main__':prepare()
