import pathlib,re,difflib,json
R=pathlib.Path(__file__).resolve().parent
# Mask comments/strings so brace matching preserves exact function text.
def mask(s):
 return re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',lambda m:' '*len(m.group()),s)
def span(s,name):
 m=re.search(r'(?m)^[ \t]*(?:static\s+)?(?:int|int32_t|ssize_t|off_t|uint32_t|uint16_t|void)\s+'+name+r'\s*\([^;{}]*\)\s*\{',mask(s));assert m,name
 start=s.rfind('\n',0,m.start())+1;opening=s.find('{',m.start());level=1;i=opening+1;clean=mask(s)
 while level:
  if clean[i]=='{':level+=1
  elif clean[i]=='}':level-=1
  i+=1
 return start,opening,i
MODS={}
def wrap(s,name,ro):
 start,brace,end=span(s,name)
 MODS.setdefault(name,ro)
 return s[:brace+1]+'\n#ifdef CONFIG_FAT_FORCE_READONLY\n'+ro+'\n#else\n'+s[brace+1:end-1]+'\n#endif\n'+s[end-1:]
def deny(s,name):
 start,brace,end=span(s,name)
 params=s[s.find('(',start)+1:s.rfind(')',start,brace)]
 names=[re.findall(r'\b\w+\b',p)[-1] for p in params.split(',')]
 return wrap(s,name,'  '+''.join('(void)'+p+'; ' for p in names)+'\n  return -EROFS;')
for filename in ['fs_fat32.c','fs_fat32util.c','fs_fat32dirent.c','fs_fat32attrib.c','fs_fat32.h','Kconfig']:
 s=(R/'input/fat'/filename).read_text()
 if filename=='fs_fat32.c':
  for name in ['fat_write','fat_truncate','fat_unlink','fat_mkdir','fat_rmdir','fat_rename','fat_zero_cluster']:s=deny(s,name)
  start,brace,end=span(s,'fat_open')
  s=s[:brace+1]+'''\n#ifdef CONFIG_FAT_FORCE_READONLY
  if ((oflags & O_ACCMODE) != O_RDONLY ||
      (oflags & (O_CREAT | O_TRUNC | O_APPEND | O_EXCL)) != 0)
    {
      return -EROFS;
    }
#endif
'''+s[brace+1:]
  s=s.replace('  ret = fat_mount(fs, true);','''#ifdef CONFIG_FAT_FORCE_READONLY
  ret = fat_mount(fs, false);
#else
  ret = fat_mount(fs, true);
#endif''')
  s=wrap(s,'fat_sync','''  FAR struct fat_file_s *ff = filep->f_priv;
  FAR struct fat_mountpt_s *fs = filep->f_inode->i_private;
  int ret;
  if ((ff->ff_bflags & UMOUNT_FORCED) != 0) return -EPIPE;
  ret = nxmutex_lock(&fs->fs_lock);
  if (ret < 0) return ret;
  ret = fat_checkmount(fs);
  if (ret == OK && ((ff->ff_bflags & (FFBUFF_DIRTY | FFBUFF_MODIFIED)) != 0 ||
                    fs->fs_dirty || fs->fs_fsidirty)) ret = -EROFS;
  nxmutex_unlock(&fs->fs_lock);
  return ret;''')
 if filename=='fs_fat32util.c':
  for name in ['fat_hwwrite','fat_putcluster','fat_removechain','fat_extendchain','fat_dirtruncate','fat_dirshrink','fat_dirextend']:s=deny(s,name)
  for name,ro in [('fat_fscacheflush','  return fs->fs_dirty ? -EROFS : OK;'),('fat_ffcacheflush','  (void)fs;\n  return (ff->ff_bflags & (FFBUFF_DIRTY | FFBUFF_MODIFIED)) ? -EROFS : OK;'),('fat_updatefsinfo','  return (fs->fs_dirty || fs->fs_fsidirty) ? -EROFS : OK;')]:s=wrap(s,name,ro)
  start,brace,end=span(s,'fat_mount');s=s[:brace+1]+'''\n#ifdef CONFIG_FAT_FORCE_READONLY
  writeable = false;
#endif
'''+s[brace+1:]
  start,brace,end=span(s,'fat_computefreeclusters');part=s[start:end]
  old='''  if (fs->fs_type == FSTYPE_FAT32)
    {
      fs->fs_fsidirty = true;
    }''';assert old in part
  part=part.replace(old,'#ifndef CONFIG_FAT_FORCE_READONLY\n'+old+'\n#endif')
  s=s[:start]+part+s[end:]
 if filename=='fs_fat32dirent.c':
  for name in ['fat_allocatedirentry','fat_freedirentry','fat_dirnamewrite','fat_dirwrite','fat_dircreate','fat_remove']:s=deny(s,name)
 if filename=='fs_fat32attrib.c':
  s=deny(s,'fat_setattrib')
  start,brace,end=span(s,'fat_attrib');s=s[:brace+1]+'''\n#ifdef CONFIG_FAT_FORCE_READONLY
  if (setbits != 0 || clearbits != 0) return -EROFS;
#endif
'''+s[brace+1:]
 if filename=='Kconfig':
  s=s.replace('if FS_FAT\n','''if FS_FAT

config FAT_FORCE_READONLY
	bool "Force all FAT mounts read-only"
	default n
	---help---
		Explicit storage-read diagnostic mode. Every FAT mount in this
		firmware accepts read-only block geometry and rejects mutations.
		No file times or FSInfo are written; the final hardware write
		entry is denied. This does not rely on VFS MS_RDONLY propagation.
		Leave disabled to retain the existing read/write FAT behavior.
''',1)
 (R/'candidate/fat'/filename).write_text(s)
 patches=list(difflib.unified_diff((R/'input/fat'/filename).read_text().splitlines(True),s.splitlines(True),fromfile='a/fs/fat/'+filename,tofile='b/fs/fat/'+filename))
 if patches:(R/'evidence'/('patch-'+filename+'.diff')).write_text(''.join(patches))
(R/'evidence/guarded-functions.json').write_text(json.dumps(MODS,indent=2))
print('candidate generated; denied',len(MODS),'guarded function branches')

