#include "compat.h"
static int fat_stat_common(FAR struct fat_mountpt_s *fs,
                           FAR uint8_t *direntry, FAR struct stat *buf)
{
  uint16_t fatdate;
  uint16_t date2;
  uint16_t fattime;

  /* Times */

  fatdate           = DIR_GETWRTDATE(direntry);
  fattime           = DIR_GETWRTTIME(direntry);
  buf->st_mtime     = fat_fattime2systime(fattime, fatdate);

  date2             = DIR_GETLASTACCDATE(direntry);
  if (fatdate == date2)
    {
      buf->st_atime = buf->st_mtime;
    }
  else
    {
      buf->st_atime = fat_fattime2systime(0, date2);
    }

  fatdate           = DIR_GETCRDATE(direntry);
  fattime           = DIR_GETCRTIME(direntry);
  buf->st_ctime     = fat_fattime2systime(fattime, fatdate);

  /* File/directory size, access block size */

  buf->st_size      = DIR_GETFILESIZE(direntry);
  buf->st_blksize   = fs->fs_fatsecperclus * fs->fs_hwsectorsize;
  buf->st_blocks    = (buf->st_size + buf->st_blksize - 1) / buf->st_blksize;

  return OK;
}
static int fat_stat_file(FAR struct fat_mountpt_s *fs,
                         FAR uint8_t *direntry, FAR struct stat *buf)
{
  uint8_t  attribute;

  /* Initialize the "struct stat" */

  memset(buf, 0, sizeof(struct stat));

  /* Get attribute from direntry */

  attribute = DIR_GETATTRIBUTES(direntry);
  if ((attribute & FATATTR_VOLUMEID) != 0)
    {
      return -ENOENT;
    }

  /* Set the access permissions.  The file/directory is always readable
   * by everyone but may be writeable by no-one.
   */

  buf->st_mode = S_IROTH | S_IRGRP | S_IRUSR;
  if ((attribute & FATATTR_READONLY) == 0)
    {
      buf->st_mode |= S_IWOTH | S_IWGRP | S_IWUSR;
    }

  /* We will report only types file or directory */

  if ((attribute & FATATTR_DIRECTORY) != 0)
    {
      buf->st_mode |= S_IFDIR;
    }
  else
    {
      buf->st_mode |= S_IFREG;
    }

  return fat_stat_common(fs, direntry, buf);
}
static int fat_fstat(FAR const struct file *filep, FAR struct stat *buf)
{
  FAR struct inode *inode;
  FAR struct fat_mountpt_s *fs;
  FAR struct fat_file_s *ff;
  uint8_t *direntry;
  int ret;

  /* Sanity checks */

  DEBUGASSERT(filep->f_priv != NULL);

  /* Get the mountpoint inode reference from the file structure and the
   * mountpoint private data from the inode structure
   */

  inode = filep->f_inode;
  fs    = inode->i_private;

  DEBUGASSERT(fs != NULL);

  /* Check if the mount is still healthy */

  ret = nxmutex_lock(&fs->fs_lock);
  if (ret < 0)
    {
      return ret;
    }

  ret = fat_checkmount(fs);
  if (ret != OK)
    {
      goto errout_with_lock;
    }

  /* Recover our private data from the struct file instance */

  ff = filep->f_priv;

  /* Update the directory entry.  First read the directory
   * entry into the fs_buffer (preserving the ff_buffer)
   */

  ret = fat_fscacheread(fs, ff->ff_dirsector);
  if (ret < 0)
    {
      goto errout_with_lock;
    }

  /* Recover a pointer to the specific directory entry in the sector using
   * the saved directory index.
   */

  direntry = &fs->fs_buffer[(ff->ff_dirindex & DIRSEC_NDXMASK(fs)) *
                             DIR_SIZE];

  /* Call fat_stat_file() to create the buf and to save information to
   * it.
   */

  ret = fat_stat_file(fs, direntry, buf);

errout_with_lock:
  nxmutex_unlock(&fs->fs_lock);
  return ret;
}
static off_t fat_seek(FAR struct file *filep, off_t offset, int whence)
{
  FAR struct inode *inode;
  FAR struct fat_mountpt_s *fs;
  FAR struct fat_file_s *ff;
  off_t position;
  int ret;

  /* Sanity checks */

  DEBUGASSERT(filep->f_priv != NULL);

  /* Recover our private data from the struct file instance */

  ff = filep->f_priv;

  /* Check for the forced mount condition */

  if ((ff->ff_bflags & UMOUNT_FORCED) != 0)
    {
      return -EPIPE;
    }

  inode = filep->f_inode;
  fs    = inode->i_private;

  DEBUGASSERT(fs != NULL);

  /* Map the offset according to the whence option */

  switch (whence)
    {
      case SEEK_SET: /* The offset is set to offset bytes. */
          position = offset;
          break;

      case SEEK_CUR: /* The offset is set to its current location plus
                      * offset bytes. */

          position = offset + filep->f_pos;
          break;

      case SEEK_END: /* The offset is set to the size of the file plus
                      * offset bytes. */

          position = offset + ff->ff_size;
          break;

      default:
          return -EINVAL;
    }

  /* Invalid arguments are entered, returns an error. */

  if (position < 0)
    {
      return -EINVAL;
    }

  /* Special case:  We are seeking to the current position.  This would
   * happen normally with ftell() which does lseek(fd, 0, SEEK_CUR) but can
   * also happen in other situation such as when SEEK_SET is used to assure
   * assure sequential access in a multi-threaded environment where there
   * may be are multiple users to the file descriptor.
   * Effectively handles the situation when a new file position is within
   * the current sector.
   */

  if (position / fs->fs_hwsectorsize == filep->f_pos / fs->fs_hwsectorsize)
    {
      filep->f_pos = position;
      return position;
    }

  /* Make sure that the mount is still healthy */

  ret = nxmutex_lock(&fs->fs_lock);
  if (ret < 0)
    {
      return ret;
    }

  ret = fat_checkmount(fs);
  if (ret != OK)
    {
      goto errout_with_lock;
    }

  /* Check if there is unwritten data in the file buffer */

  ret = fat_ffcacheflush(fs, ff);
  if (ret < 0)
    {
      goto errout_with_lock;
    }

  filep->f_pos = position;

  nxmutex_unlock(&fs->fs_lock);
  return position;

errout_with_lock:
  nxmutex_unlock(&fs->fs_lock);
  return ret;
}
/* Runs exact extracted FAT functions; cache, clock, lock and mount health mocked. */
static void size_field(uint8_t*p,uint32_t n){for(unsigned i=0;i<4;i++)p[28+i]=(uint8_t)(n>>(8*i));}
int main(void){
 uint8_t sector[512]={0};
 struct fat_mountpt_s fs={sector,0,512,8};
 struct inode ino={&fs};
 struct fat_file_s ff={0,0,123,2};
 struct file f={&ino,&ff,0};
 struct stat a,b;
 size_field(sector,123);
 memset(&a,0xa5,sizeof a);
 assert(fat_stat_file(&fs,sector,&a)==0);
 assert(a.st_dev==0 && a.st_ino==0 && a.st_size==123 && (a.st_mode&S_IFREG));
 size_field(sector+32,456);sector[32]='B';ff.ff_dirindex=1;
 assert(fat_fstat(&f,&b)==0 && b.st_size==456);
 assert(a.st_dev==b.st_dev && a.st_ino==b.st_ino);
 /* fstat uses directory cache size, not the file-open ff_size snapshot. */
 assert(ff.ff_size==123);
 cache_error=-EIO;assert(fat_fstat(&f,&b)==-EIO);cache_error=0;
 health_error=-ENODEV;assert(fat_fstat(&f,&b)==-ENODEV);health_error=0;
#if OFF_BITS == 64
 const uint32_t sizes[]={0,1,0x7fffffffU,0x80000000U,0xfffffffeU,0xffffffffU};
 for(unsigned i=0;i<sizeof sizes/sizeof sizes[0];i++){
  size_field(sector,sizes[i]);assert(fat_stat_file(&fs,sector,&a)==0);
  assert(a.st_size==(int64_t)sizes[i]);ff.ff_size=a.st_size;
  assert(fat_seek(&f,a.st_size,SEEK_SET)==a.st_size);
 }
 /* FAT permits beyond EOF; mr absolute-range check must reject it first. */
 assert(fat_seek(&f,INT64_C(0x100000000),SEEK_SET)==INT64_C(0x100000000));
 assert(fat_seek(&f,-1,SEEK_SET)==-EINVAL);
 flush_error=-EROFS;assert(fat_seek(&f,0,SEEK_SET)==-EROFS);flush_error=0;
 printf("PASS off64: FAT sizes 0..UINT32_MAX; exact SEEK_SET >2GiB; beyond EOF allowed; stat/fstat identity collision; errors preserved\n");
#else
 assert(fat_seek(&f,123,SEEK_SET)==123);
 /* Current GCC narrowing behavior, not a portable C promise for out-of-range casts. */
 size_field(sector,UINT32_MAX);assert(fat_stat_file(&fs,sector,&a)==0);
 assert(a.st_size==-1);
 printf("PASS off32 mock: UINT32_MAX narrows to -1 on this GCC; reader must require target off_t64\n");
#endif
 return 0;
}
