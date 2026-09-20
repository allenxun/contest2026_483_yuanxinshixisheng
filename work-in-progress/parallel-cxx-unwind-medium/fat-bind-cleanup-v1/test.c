#include "mock.h"

int fat_mount(struct fat_mountpt_s *fs, bool writeable)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  writeable = false;
#endif

  FAR struct inode *inode;
  struct geometry geo;
  int ret;

  /* Assume that the mount is successful */

  fs->fs_mounted = true;

  /* Check if there is media available */

  inode = fs->fs_blkdriver;
  if (!inode || !inode->u.i_bops || !inode->u.i_bops->geometry ||
      inode->u.i_bops->geometry(inode, &geo) != OK || !geo.geo_available)
    {
      ret = -ENODEV;
      goto errout;
    }

  /* Make sure that that the media is write-able (if write access is
   * needed).
   */

  if (writeable && !geo.geo_writeenabled)
    {
      ret = -EACCES;
      goto errout;
    }

  /* Save the hardware geometry */

  fs->fs_hwsectorsize = geo.geo_sectorsize;
  fs->fs_hwnsectors   = geo.geo_nsectors;

  /* Allocate a buffer to hold one hardware sector */

  fs->fs_buffer = (FAR uint8_t *)fat_io_alloc(fs->fs_hwsectorsize);
  if (!fs->fs_buffer)
    {
      ret = -ENOMEM;
      goto errout;
    }

  /* Search FAT boot record on the drive.  First check the MBR at sector
   * zero.  This could be either the boot record or a partition that refers
   * to the boot record.
   *
   * First read sector zero.  This will be the first access to the drive and
   * a likely failure point.
   */

  fs->fs_fatbase = 0;
  ret = fat_hwread(fs, fs->fs_buffer, 0, 1);
  if (ret < 0)
    {
      goto errout_with_buffer;
    }

  /* Older style MBR (pre-partition table) includes boot information for the
   * partition-less drive.  Check for that case first.
   */

  ret = fat_checkbootrecord(fs);
  if (ret != OK)
    {
      /* The contents of sector 0 is not a boot record.  It could be have
       * DOS partitions, however.  Get the offset into the partition table.
       * This table is at offset MBR_TABLE and is indexed by 16x the
       * partition number.
       */

      int i;
      for (i = 0; i < 4; i++)
        {
          /* Check if the partition exists and, if so, get the bootsector for
           * that partition and see if we can find the boot record there.
           */

          uint8_t part = PART_GETTYPE(i, fs->fs_buffer);
          finfo("Partition %d, offset %d, type %d\n",
                 i, PART_ENTRY(i), part);

          if (part == 0)
            {
              finfo("No partition %d\n", i);
              continue;
            }

          /* There appears to be a partition, get the sector number of the
           * partition (LBA)
           */

          fs->fs_fatbase = PART_GETSTARTSECTOR(i, fs->fs_buffer);

          /* Read the new candidate boot sector */

          ret = fat_hwread(fs, fs->fs_buffer, fs->fs_fatbase, 1);
          if (ret < 0)
            {
              /* Failed to read the sector */

              ferr("ERROR: Failed to read sector %ld: %d\n",
                   (long)fs->fs_fatbase, ret);
              continue;
            }

          /* Check if this is a boot record */

          ret = fat_checkbootrecord(fs);
          if (ret == OK)
            {
              /* Break out of the loop if a valid boot record is found */

              finfo("FBR found in partition %d\n", i);
              break;
            }

          /* Re-read sector 0 so that we can check the next partition */

          finfo("Partition %d is not an FBR\n", i);
          ret = fat_hwread(fs, fs->fs_buffer, 0, 1);
          if (ret < 0)
            {
              ferr("ERROR: Failed to re-read sector 0: %d\n", ret);
              goto errout_with_buffer;
            }
        }

      if (i > 3)
        {
          ferr("ERROR: No valid boot record\n");
          ret = -EINVAL;
          goto errout_with_buffer;
        }
    }

  /* We have what appears to be a valid FAT filesystem! Now read the
   * FSINFO sector (FAT32 only)
   */

  if (fs->fs_type == FSTYPE_FAT32)
    {
      ret = fat_checkfsinfo(fs);
      if (ret != OK)
        {
          goto errout_with_buffer;
        }
    }

  /* Enforce computation of free clusters if configured */

#ifdef CONFIG_FAT_COMPUTE_FSINFO
  ret = fat_computefreeclusters(fs);
  if (ret != OK)
    {
      goto errout_with_buffer;
    }
#endif

  /* We did it! */

  finfo("FAT%d:\n", fs->fs_type == 0 ? 12 : fs->fs_type == 1  ? 16 : 32);
  finfo("\tHW  sector size:     %" PRIdOFF "\n", fs->fs_hwsectorsize);
  finfo("\t    sectors:         %" PRIdOFF "\n", fs->fs_hwnsectors);
  finfo("\tFAT reserved:        %d\n", fs->fs_fatresvdseccount);
  finfo("\t    sectors:         %" PRId32 "\n", fs->fs_fattotsec);
  finfo("\t    start sector:    %" PRIdOFF "\n", fs->fs_fatbase);
  finfo("\t    root sector:     %" PRIdOFF "\n", fs->fs_rootbase);
  finfo("\t    root entries:    %d\n", fs->fs_rootentcnt);
  finfo("\t    data sector:     %" PRIdOFF "\n", fs->fs_database);
  finfo("\t    FSINFO sector:   %" PRIdOFF "\n", fs->fs_fsinfo);
  finfo("\t    Num FATs:        %d\n", fs->fs_fatnumfats);
  finfo("\t    FAT sectors:     %" PRId32 "\n", fs->fs_nfatsects);
  finfo("\t    sectors/cluster: %d\n", fs->fs_fatsecperclus);
  finfo("\t    max clusters:    %" PRId32 "\n", fs->fs_nclusters);
  finfo("\tFSI free count       %" PRId32 "\n", fs->fs_fsifreecount);
  finfo("\t    next free        %" PRId32 "\n", fs->fs_fsinextfree);

  return OK;

errout_with_buffer:
  fat_io_free(fs->fs_buffer, fs->fs_hwsectorsize);
  fs->fs_buffer = NULL;

errout:
  fs->fs_mounted = false;
  return ret;
}
static int fat_bind(FAR struct inode *blkdriver, FAR const void *data,
                    FAR void **handle)
{
  FAR struct fat_mountpt_s *fs;
  int ret;
  bool opened = false;

  /* Open the block driver */

  if (!blkdriver || !blkdriver->u.i_bops)
    {
      return -ENODEV;
    }

  if (blkdriver->u.i_bops->open &&
      blkdriver->u.i_bops->open(blkdriver) != OK)
    {
      return -ENODEV;
    }

  opened = blkdriver->u.i_bops->open != NULL;

  /* Create an instance of the mountpt state structure */

  fs = fs_heap_zalloc(sizeof(struct fat_mountpt_s));
  if (!fs)
    {
      ret = -ENOMEM;
      goto errout_with_open;
    }

  /* Initialize the allocated mountpt state structure.  The filesystem is
   * responsible for one reference on the blkdriver inode and does not
   * have to addref() here (but does have to release in unbind().
   */

  fs->fs_blkdriver = blkdriver;   /* Save the block driver reference */
  nxmutex_init(&fs->fs_lock);     /* Initialize the mutex that controls access */

  /* Then get information about the FAT32 filesystem on the devices managed
   * by this block driver.
   */

#ifdef CONFIG_FAT_FORCE_READONLY
  ret = fat_mount(fs, false);
#else
  ret = fat_mount(fs, true);
#endif
  if (ret != 0)
    {
      nxmutex_destroy(&fs->fs_lock);
      fs_heap_free(fs);
      goto errout_with_open;
    }

  *handle = (FAR void *)fs;
  return OK;

errout_with_open:
  /* VFS drops its inode reference on bind failure; only FAT owns this
   * successful block open. Preserve the primary failure if close fails. */

  if (opened && blkdriver->u.i_bops->close)
    {
      blkdriver->u.i_bops->close(blkdriver);
    }

  return ret;
}
static int fat_unbind(FAR void *handle, FAR struct inode **blkdriver,
                      unsigned int flags)
{
  FAR struct fat_mountpt_s *fs = (FAR struct fat_mountpt_s *)handle;
  int ret;

  if (!fs)
    {
      return -EINVAL;
    }

  /* Check if there are sill any files opened on the filesystem. */

  ret = nxmutex_lock(&fs->fs_lock);
  if (ret < 0)
    {
      return ret;
    }

  if (fs->fs_head)
    {
      /* There are open files.  We umount now unless we are forced with the
       * MNT_FORCE flag.  Forcing the unmount will cause data loss because
       * the filesystem buffers are not flushed to the media. MNT_DETACH,
       * the 'lazy' unmount, could be implemented to fix this.
       */

      if ((flags & MNT_FORCE) != 0)
        {
          FAR struct fat_file_s *ff;

          /* Set a flag in each open file structure.  This flag will signal
           * the file system to fail any subsequent attempts to used the
           * file handle.
           */

          for (ff = fs->fs_head; ff; ff = ff->ff_next)
            {
              ff->ff_bflags |= UMOUNT_FORCED;
            }
        }
      else
        {
          /* We cannot unmount now.. there are open files.  This
           * implementation does not support any other umount2()
           * options.
           */

          nxmutex_unlock(&fs->fs_lock);
          return (flags != 0) ? -ENOSYS : -EBUSY;
        }
    }

  /* Unmount ... close the block driver */

  if (fs->fs_blkdriver)
    {
      FAR struct inode *inode = fs->fs_blkdriver;
      if (inode)
        {
          if (inode->u.i_bops && inode->u.i_bops->close)
            {
              inode->u.i_bops->close(inode);
            }

          /* We hold a reference to the block driver but should not but
           * mucking with inodes in this context.  So, we will just return
           * our contained reference to the block driver inode and let the
           * umount logic dispose of it.
           */

          if (blkdriver)
            {
              *blkdriver = inode;
            }
        }
    }

  /* Release the mountpoint private data */

  if (fs->fs_buffer)
    {
      fat_io_free(fs->fs_buffer, fs->fs_hwsectorsize);
    }

  nxmutex_destroy(&fs->fs_lock);
  fs_heap_free(fs);
  return OK;
}
#include "tests.inc"
