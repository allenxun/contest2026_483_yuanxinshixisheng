#include "compat.h"
int fat_hwread(struct fat_mountpt_s *fs, uint8_t *buffer,  off_t sector,
               unsigned int nsectors)
{
  int ret = -ENODEV;
  if (fs && fs->fs_blkdriver)
    {
      struct inode *inode = fs->fs_blkdriver;
      if (inode && inode->u.i_bops && inode->u.i_bops->read)
        {
          ssize_t nsectorsread = inode->u.i_bops->read(inode, buffer,
                                                       sector, nsectors);
          if (nsectorsread == nsectors)
            {
              ret = OK;
            }
          else if (nsectorsread < 0)
            {
              ret = nsectorsread;
            }
        }
    }

  return ret;
}
int fat_hwwrite(struct fat_mountpt_s *fs, uint8_t *buffer, off_t sector,
                unsigned int nsectors)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)buffer; (void)sector; (void)nsectors; 
  return -EROFS;
#else

  int ret = -ENODEV;
  if (fs && fs->fs_blkdriver)
    {
      struct inode *inode = fs->fs_blkdriver;
      if (inode && inode->u.i_bops && inode->u.i_bops->write)
        {
          ssize_t nsectorswritten =
              inode->u.i_bops->write(inode, buffer, sector, nsectors);

          if (nsectorswritten == nsectors)
            {
              ret = OK;
            }
          else if (nsectorswritten < 0)
            {
              ret = nsectorswritten;
            }
        }
    }

  return ret;

#endif
}
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
int fat_checkmount(struct fat_mountpt_s *fs)
{
  /* If the fs_mounted flag is false, then we have already handled the loss
   * of the mount.
   */

  if (fs && fs->fs_mounted)
    {
      /* We still think the mount is healthy.  Check an see if this is
       * still the case
       */

      if (fs->fs_blkdriver)
        {
          struct inode *inode = fs->fs_blkdriver;
          if (inode && inode->u.i_bops && inode->u.i_bops->geometry)
            {
              struct geometry geo;
              int errcode = inode->u.i_bops->geometry(inode, &geo);
              if (errcode == OK && geo.geo_available &&
                  !geo.geo_mediachanged)
                {
                  return OK;
                }
            }
        }

      /* If we get here, the mount is NOT healthy */

      fs->fs_mounted = false;
    }

  return -ENODEV;
}
int fat_fscacheflush(struct fat_mountpt_s *fs)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  return fs->fs_dirty ? -EROFS : OK;
#else

  int ret;

  /* Check if the fs_buffer is dirty.  In this case, we will write back the
   * contents of fs_buffer.
   */

  if (fs->fs_dirty)
    {
      /* Write the dirty sector */

      ret = fat_hwwrite(fs, fs->fs_buffer, fs->fs_currentsector, 1);
      if (ret < 0)
        {
          return ret;
        }

      /* Does the sector lie in the FAT region? */

      if (fs->fs_currentsector >= fs->fs_fatbase &&
          fs->fs_currentsector < fs->fs_fatbase + fs->fs_nfatsects)
        {
          int i;

          /* Yes, then make the change in the FAT copy as well */

          for (i = fs->fs_fatnumfats; i >= 2; i--)
            {
              fs->fs_currentsector += fs->fs_nfatsects;
              ret = fat_hwwrite(fs, fs->fs_buffer, fs->fs_currentsector, 1);
              if (ret < 0)
                {
                  return ret;
                }
            }
        }

      /* No longer dirty */

      fs->fs_dirty = false;
    }

  return OK;

#endif
}
int fat_ffcacheflush(struct fat_mountpt_s *fs, struct fat_file_s *ff)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs;
  return (ff->ff_bflags & (FFBUFF_DIRTY | FFBUFF_MODIFIED)) ? -EROFS : OK;
#else

  int ret;

  /* Check if the ff_buffer is dirty.  In this case, we will write back the
   * contents of ff_buffer.
   */

  if (ff->ff_cachesector &&
      (ff->ff_bflags & (FFBUFF_DIRTY | FFBUFF_VALID)) ==
       (FFBUFF_DIRTY | FFBUFF_VALID))
    {
      /* Write the dirty sector */

      ret = fat_hwwrite(fs, ff->ff_buffer, ff->ff_cachesector, 1);
      if (ret < 0)
        {
          return ret;
        }

      /* No longer dirty, but still valid */

      ff->ff_bflags &= ~FFBUFF_DIRTY;
    }

  return OK;

#endif
}
int fat_fscacheread(struct fat_mountpt_s *fs, off_t sector)
{
  int ret;

  /* fs->fs_currentsector holds the current sector that is buffered in
   * fs->fs_buffer. If the requested sector is the same as this sector, then
   * we do nothing. Otherwise, we will have to read the new sector.
   */

  if (fs->fs_currentsector != sector)
    {
      /* We will need to read the new sector.  First, flush the cached
       * sector if it is dirty.
       */

      ret = fat_fscacheflush(fs);
      if (ret < 0)
        {
          return ret;
        }

      /* Then read the specified sector into the cache */

      ret = fat_hwread(fs, fs->fs_buffer, sector, 1);
      if (ret < 0)
        {
          return ret;
        }

      /* Update the cached sector number */

      fs->fs_currentsector = sector;
    }

  return OK;
}
int fat_ffcacheread(struct fat_mountpt_s *fs, struct fat_file_s *ff,
                    off_t sector)
{
  int ret;

  /* ff->ff_cachesector holds the current sector that is buffered in
   * ff->ff_buffer. If the requested sector is the same as this sector, then
   * we do nothing. Otherwise, we will have to read the new sector.
   */

  if (ff->ff_cachesector != sector || (ff->ff_bflags & FFBUFF_VALID) == 0)
    {
      /* We will need to read the new sector.  First, flush the cached
       * sector if it is dirty.
       */

      ret = fat_ffcacheflush(fs, ff);
      if (ret < 0)
        {
          return ret;
        }

      /* Then read the specified sector into the cache */

      ret = fat_hwread(fs, ff->ff_buffer, sector, 1);
      if (ret < 0)
        {
          return ret;
        }

      /* Update the cached sector number */

      ff->ff_cachesector = sector;
      ff->ff_bflags |= FFBUFF_VALID;
    }

  return OK;
}
int fat_ffcacheinvalidate(struct fat_mountpt_s *fs, struct fat_file_s *ff)
{
  int ret;

  /* Is there anything valid in the buffer now? */

  if ((ff->ff_bflags & FFBUFF_VALID) != 0)
    {
      /* We will invalidate the buffered sector */

      ret = fat_ffcacheflush(fs, ff);
      if (ret < 0)
        {
          return ret;
        }

      /* Then discard the current cache contents */

      ff->ff_bflags     &= ~FFBUFF_VALID;
      ff->ff_cachesector = 0;
    }

  return OK;
}
int fat_updatefsinfo(struct fat_mountpt_s *fs)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  return (fs->fs_dirty || fs->fs_fsidirty) ? -EROFS : OK;
#else

  int ret;

  /* Flush the fs_buffer if it is dirty */

  ret = fat_fscacheflush(fs);
  if (ret == OK)
    {
      /* The FSINFO sector only has to be update for the case of a FAT32 file
       * system.  Check if the file system type.. If this is a FAT32 file
       * system then the fs_fsidirty flag will indicate if the FSINFO sector
       * needs to be re-written.
       */

      if (fs->fs_type == FSTYPE_FAT32 && fs->fs_fsidirty)
        {
          /* Create an image of the FSINFO sector in the fs_buffer */

          memset(fs->fs_buffer, 0, fs->fs_hwsectorsize);
          FSI_PUTLEADSIG(fs->fs_buffer, 0x41615252);
          FSI_PUTSTRUCTSIG(fs->fs_buffer, 0x61417272);
          FSI_PUTFREECOUNT(fs->fs_buffer, fs->fs_fsifreecount);
          FSI_PUTNXTFREE(fs->fs_buffer, fs->fs_fsinextfree);
          FSI_PUTTRAILSIG(fs->fs_buffer, BOOT_SIGNATURE32);

          /* Then flush this to disk */

          fs->fs_currentsector = fs->fs_fsinfo;
          fs->fs_dirty         = true;
          ret                  = fat_fscacheflush(fs);

          /* No longer dirty */

          fs->fs_fsidirty = false;
        }
    }

  return ret;

#endif
}
int fat_computefreeclusters(struct fat_mountpt_s *fs)
{
  /* We have to count the number of free clusters */

  uint32_t nfreeclusters = 0;
  if (fs->fs_type == FSTYPE_FAT12)
    {
      off_t sector;

      /* Examine every cluster in the fat */

      for (sector = 2; sector < fs->fs_nclusters + 2; sector++)
        {
          /* If the cluster is unassigned, then increment the count of free
           * clusters
           */

          if ((uint16_t)fat_getcluster(fs, sector) == 0)
            {
              nfreeclusters++;
            }
        }
    }
  else
    {
      unsigned int cluster;
      off_t        fatsector;
      unsigned int offset;
      int          ret;

      fatsector    = fs->fs_fatbase;
      offset       = fs->fs_hwsectorsize;

      /* Examine each cluster in the fat */

      for (cluster = fs->fs_nclusters; cluster > 0; cluster--)
        {
          /* If we are starting a new sector, then read the new sector in
           * fs_buffer
           */

          if (offset >= fs->fs_hwsectorsize)
            {
              ret = fat_fscacheread(fs, fatsector);
              if (ret < 0)
                {
                  return ret;
                }

              /* Reset the offset to the next FAT entry.
               * Increment the sector number to read next time around.
               */

              offset = 0;
              fatsector++;
            }

          /* FAT16 and FAT32 differ only on the size of each cluster start
           * sector number in the FAT.
           */

          if (fs->fs_type == FSTYPE_FAT16)
            {
              if (FAT_GETFAT16(fs->fs_buffer, offset) == 0)
                {
                  nfreeclusters++;
                }

              offset += 2;
            }
          else
            {
              if (FAT_GETFAT32(fs->fs_buffer, offset) == 0)
                {
                  nfreeclusters++;
                }

              offset += 4;
            }
        }
    }

  fs->fs_fsifreecount = nfreeclusters;
#ifndef CONFIG_FAT_FORCE_READONLY
  if (fs->fs_type == FSTYPE_FAT32)
    {
      fs->fs_fsidirty = true;
    }
#endif

  return OK;
}
static int fat_sync(FAR struct file *filep)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  FAR struct fat_file_s *ff = filep->f_priv;
  FAR struct fat_mountpt_s *fs = filep->f_inode->i_private;
  int ret;
  if ((ff->ff_bflags & UMOUNT_FORCED) != 0) return -EPIPE;
  ret = nxmutex_lock(&fs->fs_lock);
  if (ret < 0) return ret;
  ret = fat_checkmount(fs);
  if (ret == OK && ((ff->ff_bflags & (FFBUFF_DIRTY | FFBUFF_MODIFIED)) != 0 ||
                    fs->fs_dirty || fs->fs_fsidirty)) ret = -EROFS;
  nxmutex_unlock(&fs->fs_lock);
  return ret;
#else

  FAR struct inode *inode;
  FAR struct fat_mountpt_s *fs;
  FAR struct fat_file_s *ff;
  uint32_t wrttime;
  uint8_t *direntry;
  int ret;

  /* Sanity checks */

  DEBUGASSERT(filep->f_priv != NULL);

  /* Check for the forced mount condition */

  ff = filep->f_priv;
  if ((ff->ff_bflags & UMOUNT_FORCED) != 0)
    {
      return -EPIPE;
    }

  /* Recover our private data from the struct file instance */

  inode = filep->f_inode;
  fs    = inode->i_private;

  DEBUGASSERT(fs != NULL);

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

  /* Check if the has been modified in any way */

  if ((ff->ff_bflags & FFBUFF_MODIFIED) != 0)
    {
      uint8_t dircopy[DIR_SIZE];

      /* Flush any unwritten data in the file buffer */

      ret = fat_ffcacheflush(fs, ff);
      if (ret < 0)
        {
          goto errout_with_lock;
        }

      /* Update the directory entry.  First read the directory
       * entry into the fs_buffer (preserving the ff_buffer)
       */

      ret = fat_fscacheread(fs, ff->ff_dirsector);
      if (ret < 0)
        {
          goto errout_with_lock;
        }

      /* Recover a pointer to the specific directory entry
       * in the sector using the saved directory index.
       */

      direntry = &fs->fs_buffer[(ff->ff_dirindex & DIRSEC_NDXMASK(fs)) *
                                 DIR_SIZE];

      /* Copy directory entry */

      memcpy(dircopy, direntry, DIR_SIZE);

      /* Set the archive bit, set the write time, and update
       * anything that may have* changed in the directory
       * entry: the file size, and the start cluster
       */

      direntry[DIR_ATTRIBUTES] |= FATATTR_ARCHIVE;

      DIR_PUTFILESIZE(direntry, ff->ff_size);
      DIR_PUTFSTCLUSTLO(direntry, ff->ff_startcluster);
      DIR_PUTFSTCLUSTHI(direntry, ff->ff_startcluster >> 16);

      wrttime = fat_systime2fattime();
      DIR_PUTWRTTIME(direntry, wrttime & 0xffff);
      DIR_PUTWRTDATE(direntry, wrttime >> 16);

      /* Clear the modified bit in the flags */

      ff->ff_bflags &= ~FFBUFF_MODIFIED;

      /* Compare old and new directory entry */

      if (memcmp(direntry, dircopy, DIR_SIZE) != 0)
        {
          fs->fs_dirty = true;
        }

      /* Flush these change to disk and update FSINFO (if
       * appropriate.
       */

      ret          = fat_updatefsinfo(fs);
    }

errout_with_lock:
  nxmutex_unlock(&fs->fs_lock);
  return ret;

#endif
}
static ssize_t fat_read(FAR struct file *filep, FAR char *buffer,
                        size_t buflen)
{
  FAR struct inode *inode;
  FAR struct fat_mountpt_s *fs;
  FAR struct fat_file_s *ff;
  unsigned int bytesread;
  unsigned int readsize;
  size_t bytesleft;
  FAR uint8_t *userbuffer = (FAR uint8_t *)buffer;
  int sectorindex;
  int ret;

#ifndef CONFIG_FAT_FORCE_INDIRECT
  unsigned int nsectors;
  bool force_indirect = false;
#endif

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

  /* Check if the file was opened with read access */

  if ((ff->ff_oflags & O_RDOK) == 0)
    {
      ret = -EACCES;
      goto errout_with_lock;
    }

  /* Check that the file position is not past the end of the file */

  if (filep->f_pos > ff->ff_size)
    {
      /* Return EOF */

      ret = 0;
      goto errout_with_lock;
    }
  else
    {
      /* Get the number of bytes left in the file */

      bytesleft = ff->ff_size - filep->f_pos;

      /* Truncate read count so that it does not exceed the number of bytes
       * left in the file.
       */

      if (buflen > bytesleft)
        {
          buflen = bytesleft;
        }
    }

  /* Loop until either (1) all data has been transferred, or (2) an error
   * occurs.  We assume we start with the current sector (ff_currentsector)
   * which may be uninitialized.
   */

  readsize    = 0;
  sectorindex = filep->f_pos & SEC_NDXMASK(fs);

  while (buflen > 0)
    {
      bytesread  = 0;

      ret = fat_get_sectors(filep, true);
      if (ret < 0)
        {
          goto errout_with_lock;
        }

#ifdef CONFIG_FAT_DIRECT_RETRY /* Warning avoidance */
fat_read_restart:
#endif

#ifndef CONFIG_FAT_FORCE_INDIRECT
      /* Check if the user has provided a buffer large enough to hold one
       * or more complete sectors -AND- the read is aligned to a sector
       * boundary.
       */

      nsectors = buflen / fs->fs_hwsectorsize;
      if (nsectors > 0 && sectorindex == 0 && !force_indirect)
        {
          /* Read maximum contiguous sectors directly to the user's
           * buffer without using our tiny read buffer.
           *
           * Limit the number of sectors that we read on this time
           * through the loop to the remaining contiguous sectors
           * in this cluster
           */

          if (nsectors > ff->ff_sectorsincluster)
            {
              nsectors = ff->ff_sectorsincluster;
            }

          /* We are not sure of the state of the file buffer so
           * the safest thing to do is just invalidate it
           */

          fat_ffcacheinvalidate(fs, ff);

          /* Read all of the sectors directly into user memory */

          ret = fat_hwread(fs, userbuffer, ff->ff_currentsector, nsectors);
          if (ret < 0)
            {
#ifdef CONFIG_FAT_DIRECT_RETRY
              /* The low-level driver may return -EFAULT in the case where
               * the transfer cannot be performed due to buffer memory
               * constraints.  It is probable that the buffer is completely
               * un-DMA-able or improperly aligned.  In this case, force
               * indirect transfers via the sector buffer and restart the
               * operation (unless we have already tried that).
               */

              if (ret == -EFAULT && !force_indirect)
                {
                  ferr("ERROR: DMA read alignment error,"
                       " restarting indirect\n");
                  force_indirect = true;
                  goto fat_read_restart;
                }
#endif /* CONFIG_FAT_DIRECT_RETRY */

              goto errout_with_lock;
            }

          ff->ff_sectorsincluster -= nsectors;
          ff->ff_currentsector    += nsectors;
          bytesread                = nsectors * fs->fs_hwsectorsize;
        }
      else
#endif /* CONFIG_FAT_FORCE_INDIRECT */
        {
          /* We are reading a partial sector, or handling a non-DMA-able
           * whole-sector transfer.  First, read the whole sector
           * into the file data buffer.  This is a caching buffer so if
           * it is already there then all is well.
           */

          ret = fat_ffcacheread(fs, ff, ff->ff_currentsector);
          if (ret < 0)
            {
              goto errout_with_lock;
            }

          /* Copy the requested part of the sector into the user buffer */

          bytesread = fs->fs_hwsectorsize - sectorindex;
          if (bytesread > buflen)
            {
              /* We will not read to the end of the buffer */

              bytesread = buflen;
            }
          else
            {
              /* We will read to the end of the buffer (or beyond) */

              ff->ff_sectorsincluster--;
              ff->ff_currentsector++;
            }

          memcpy(userbuffer, &ff->ff_buffer[sectorindex], bytesread);
        }

      /* Set up for the next sector read */

      userbuffer   += bytesread;
      filep->f_pos += bytesread;
      readsize     += bytesread;
      buflen       -= bytesread;
      sectorindex   = filep->f_pos & SEC_NDXMASK(fs);
    }

  nxmutex_unlock(&fs->fs_lock);
  return readsize;

errout_with_lock:
  nxmutex_unlock(&fs->fs_lock);
  return ret;
}
static int fat_close(FAR struct file *filep)
{
  FAR struct inode *inode;
  FAR struct fat_file_s *ff;
  FAR struct fat_file_s *currff;
  FAR struct fat_file_s *prevff;
  FAR struct fat_mountpt_s *fs;
  int ret = OK;

  /* Sanity checks */

  DEBUGASSERT(filep->f_priv != NULL);

  /* Recover our private data from the struct file instance */

  ff    = filep->f_priv;
  inode = filep->f_inode;
  fs    = inode->i_private;

  DEBUGASSERT(fs != NULL);

  /* Check for the forced mount condition */

  if ((ff->ff_bflags & UMOUNT_FORCED) == 0)
    {
      /* Do not check if the mount is healthy.  We must support closing of
       * the file even when there is healthy mount.
       */

      /* Synchronize the file buffers and disk content; update times */

      ret = fat_sync(filep);

      /* Remove the file structure from the list of open files in the
       * mountpoint structure.
       */

      for (prevff = NULL, currff = fs->fs_head;
           currff && currff != ff;
           prevff = currff, currff = currff->ff_next);

      if (currff)
        {
          if (prevff)
            {
              prevff->ff_next = ff->ff_next;
            }
          else
            {
              fs->fs_head = ff->ff_next;
            }
        }
    }

  /* Then deallocate the memory structures created when the open method
   * was called.
   *
   * Free the sector buffer that was used to manage partial sector accesses.
   */

  if (ff->ff_buffer)
    {
      fat_io_free(ff->ff_buffer, fs->fs_hwsectorsize);
    }

  /* Then free the file structure itself. */

  fs_heap_free(ff);
  filep->f_priv = NULL;
  return ret;
}
static int fat_bind(FAR struct inode *blkdriver, FAR const void *data,
                    FAR void **handle)
{
  FAR struct fat_mountpt_s *fs;
  int ret;

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

  /* Create an instance of the mountpt state structure */

  fs = fs_heap_zalloc(sizeof(struct fat_mountpt_s));
  if (!fs)
    {
      return -ENOMEM;
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
      return ret;
    }

  *handle = (FAR void *)fs;
  return OK;
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
static ssize_t fat_write(FAR struct file *filep, FAR const char *buffer,
                         size_t buflen)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)filep; (void)buffer; (void)buflen; 
  return -EROFS;
#else

  FAR struct inode *inode;
  FAR struct fat_mountpt_s *fs;
  FAR struct fat_file_s *ff;
  unsigned int byteswritten;
  unsigned int writesize;
  FAR uint8_t *userbuffer = (FAR uint8_t *)buffer;
  int sectorindex;
  int ret;

#ifndef CONFIG_FAT_FORCE_INDIRECT
  unsigned int nsectors;
  bool force_indirect = false;
#endif

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

  /* Check if the file was opened for write access */

  if ((ff->ff_oflags & O_WROK) == 0)
    {
      ret = -EACCES;
      goto errout_with_lock;
    }

  /* Check if the file size would exceed the range of off_t */

  if (buflen > OFF_MAX || ff->ff_size > OFF_MAX - (off_t)buflen)
    {
      ret = -EFBIG;
      goto errout_with_lock;
    }

  /* Loop until either (1) all data has been transferred, or (2) an
   * error occurs.  We assume we start with the current sector in
   * cache (ff_currentsector)
   */

  byteswritten = 0;
  sectorindex = filep->f_pos & SEC_NDXMASK(fs);

  while (buflen > 0)
    {
      ret = fat_get_sectors(filep, false);
      if (ret < 0)
        {
          goto errout_with_lock;
        }

#ifdef CONFIG_FAT_DIRECT_RETRY /* Warning avoidance */
fat_write_restart:
#endif

#ifndef CONFIG_FAT_FORCE_INDIRECT
      /* Check if the user has provided a buffer large enough to
       * hold one or more complete sectors.
       */

      nsectors = buflen / fs->fs_hwsectorsize;
      if (nsectors > 0 && sectorindex == 0 && !force_indirect)
        {
          /* Write maximum contiguous sectors directly from the user's
           * buffer without using our tiny read buffer.
           *
           * Limit the number of sectors that we write on this time
           * through the loop to the remaining contiguous sectors
           * in this cluster
           */

          if (nsectors > ff->ff_sectorsincluster)
            {
              nsectors = ff->ff_sectorsincluster;
            }

          /* We are not sure of the state of the sector cache so the
           * safest thing to do is write back any dirty, cached sector
           * and invalidate the current cache content.
           */

          fat_ffcacheinvalidate(fs, ff);

          /* Write all of the sectors directly from user memory */

          ret = fat_hwwrite(fs, userbuffer, ff->ff_currentsector, nsectors);
          if (ret < 0)
            {
#ifdef CONFIG_FAT_DIRECT_RETRY
              /* The low-level driver may return -EFAULT in the case where
               * the transfer cannot be performed due to buffer memory
               * constraints.  It is probable that the buffer is completely
               * un-DMA-able or improperly aligned.  In this case, force
               * indirect transfers via the sector buffer and restart the
               * operation (unless we have already tried that).
               */

              if (ret == -EFAULT && !force_indirect)
                {
                  ferr("ERROR: DMA write alignment error,"
                        " restarting indirect\n");
                  force_indirect = true;
                  goto fat_write_restart;
                }
#endif /* CONFIG_FAT_DIRECT_RETRY */

              goto errout_with_lock;
            }

          ff->ff_sectorsincluster -= nsectors;
          ff->ff_currentsector    += nsectors;
          writesize                = nsectors * fs->fs_hwsectorsize;
          ff->ff_bflags           |= FFBUFF_MODIFIED;
        }
      else
#endif /* CONFIG_FAT_FORCE_INDIRECT */
        {
          /* Decide whether we are performing a read-modify-write
           * operation, in which case we have to read the existing sector
           * into the buffer first.
           *
           * There are two cases where we can avoid this read:
           *
           * - If we are performing a whole-sector write that was rejected
           *   by fat_hwwrite(), i.e. sectorindex == 0 and buflen >= sector
           *   size.
           *
           * - If the write is aligned to the beginning of the sector and
           *   extends beyond the end of the file, i.e. sectorindex == 0 and
           *   file pos + buflen >= file size.
           */

          if ((sectorindex == 0) && ((buflen >= fs->fs_hwsectorsize) ||
              ((filep->f_pos + buflen) >= ff->ff_size)))
            {
              /* Flush unwritten data in the sector cache. */

              ret = fat_ffcacheflush(fs, ff);
              if (ret < 0)
                {
                  goto errout_with_lock;
                }

              /* Now mark the clean cache buffer as the current sector. */

              ff->ff_cachesector = ff->ff_currentsector;
            }
          else
            {
              /* Read the current sector into memory (perhaps first flushing
               * the old, dirty sector to disk).
               */

              ret = fat_ffcacheread(fs, ff, ff->ff_currentsector);
              if (ret < 0)
                {
                  goto errout_with_lock;
                }
            }

          /* Copy the requested part of the sector from the user buffer */

          writesize = fs->fs_hwsectorsize - sectorindex;
          if (writesize > buflen)
            {
              /* We will not write to the end of the buffer.  Set
               * write size to the size of the user buffer.
               */

              writesize = buflen;
            }
          else
            {
              /* We will write to the end of the buffer (or beyond).  Bump
               * up the current sector number (actually the next sector
               * number).
               */

              ff->ff_sectorsincluster--;
              ff->ff_currentsector++;
            }

          /* Copy the data into the cached sector and make sure that the
           * cached sector is marked "dirty"
           */

          memcpy(&ff->ff_buffer[sectorindex], userbuffer, writesize);
          ff->ff_bflags |= (FFBUFF_DIRTY | FFBUFF_VALID | FFBUFF_MODIFIED);
        }

      /* Set up for the next write */

      userbuffer   += writesize;
      filep->f_pos += writesize;
      byteswritten += writesize;
      buflen       -= writesize;
      sectorindex   = filep->f_pos & SEC_NDXMASK(fs);

      /* Update the file size */

      if (filep->f_pos > ff->ff_size)
        {
          ff->ff_size = filep->f_pos;
        }
    }

  nxmutex_unlock(&fs->fs_lock);
  return byteswritten;

errout_with_lock:
  nxmutex_unlock(&fs->fs_lock);
  return ret;

#endif
}
static int fat_truncate(FAR struct file *filep, off_t length)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)filep; (void)length; 
  return -EROFS;
#else

  FAR struct inode *inode;
  FAR struct fat_mountpt_s *fs;
  FAR struct fat_file_s *ff;
  off_t oldsize;
  int ret;

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

  /* Check if the file was opened for write access */

  if ((ff->ff_oflags & O_WROK) == 0)
    {
      ret = -EACCES;
      goto errout_with_lock;
    }

  /* Are we shrinking the file?  Or extending it? */

  oldsize = ff->ff_size;
  if (oldsize == length)
    {
      /* Do nothing but say that we did */

      ret = OK;
    }
  else if (oldsize > length)
    {
      FAR uint8_t *direntry;
      int ndx;

      /* We are shrinking the file.
       *
       * Read the directory entry into the fs_buffer.
       */

      ret = fat_fscacheread(fs, ff->ff_dirsector);
      if (ret < 0)
        {
          goto errout_with_lock;
        }

      /* Recover a pointer to the specific directory entry in the sector
       * using the saved directory index.
       */

      ndx      = (ff->ff_dirindex & DIRSEC_NDXMASK(fs)) * DIR_SIZE;
      direntry = &fs->fs_buffer[ndx];

      /* Handle the simple case where we are shrinking the file to zero
       * length.
       */

      if (length == 0)
        {
          /* Shrink to length == 0 */

          ret = fat_dirtruncate(fs, direntry);
        }
      else
        {
          /* Shrink to 0 < length < oldsize */

          ret = fat_dirshrink(fs, direntry, length);
        }

      if (ret >= 0)
        {
          /* The truncation has completed without error.  Update the file
           * size.
           */

          ff->ff_size = length;
          ret = OK;
        }
    }
  else
    {
      /* Otherwise we are extending the file.  This is essentially the same
       * as a write except that (1) we write zeros and (2) we don't update
       * the file position.
       */

      ret = fat_dirextend(fs, ff, length);
      if (ret >= 0)
        {
          /* The truncation has completed without error.  Update the file
           * size.
           */

          ff->ff_size = length;
          ret = OK;
        }
    }

errout_with_lock:
  nxmutex_unlock(&fs->fs_lock);
  return ret;

#endif
}
static int fat_unlink(FAR struct inode *mountpt, FAR const char *relpath)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)mountpt; (void)relpath; 
  return -EROFS;
#else

  FAR struct fat_mountpt_s *fs;
  int ret;

  /* Sanity checks */

  DEBUGASSERT(mountpt && mountpt->i_private);

  /* Get the mountpoint private data from the inode structure */

  fs = mountpt->i_private;

  /* Check if the mount is still healthy */

  ret = nxmutex_lock(&fs->fs_lock);
  if (ret < 0)
    {
      return ret;
    }

  ret = fat_checkmount(fs);
  if (ret == OK)
    {
      /* If the file is open, the correct behavior is to remove the file
       * name, but to keep the file cluster chain in place until the last
       * open reference to the file is closed.
       */

      /* Remove the file
       *
       * TODO: Need to defer deleting cluster chain if the file is open.
       */

      ret = fat_remove(fs, relpath, false);
    }

  nxmutex_unlock(&fs->fs_lock);
  return ret;

#endif
}
static int fat_mkdir(FAR struct inode *mountpt, FAR const char *relpath,
                     mode_t mode)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)mountpt; (void)relpath; (void)mode; 
  return -EROFS;
#else

  FAR struct fat_mountpt_s *fs;
  FAR struct fat_dirinfo_s dirinfo;
  FAR uint8_t *direntry;
  FAR uint8_t *direntry2;
  off_t parentsector;
  off_t dirsector;
  int32_t dircluster;
  uint32_t parentcluster;
  uint32_t crtime;
  unsigned int i;
  int ret;

  /* Sanity checks */

  DEBUGASSERT(mountpt && mountpt->i_private);

  /* Get the mountpoint private data from the inode structure */

  fs = mountpt->i_private;

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

  /* Find the directory where the new directory should be created. */

  ret = fat_finddirentry(fs, &dirinfo, relpath);

  /* Or if any error occurs other -ENOENT, then return the error.  For
   * example, if one of the earlier directory path segments was not found
   * then ENOTDIR will be returned.
   */

  if (ret != -ENOENT)
    {
      /* If anything exists at this location, then we fail with EEXIST */

      if (ret == OK)
        {
          ret = -EEXIST;
        }

      goto errout_with_lock;
    }

  /* What we want to see is for fat_finddirentry to fail with -ENOENT.
   * This error means that no failure occurred but that nothing exists
   * with this name.  NOTE:  The name has already been set in dirinfo
   * structure.
   */

  if (ret != -ENOENT)
    {
      goto errout_with_lock;
    }

  /* NOTE: There is no check that dirinfo.fd_name contains the final
   * directory name.  We could be creating an intermediate directory
   * in the full relpath.
   */

  /* Allocate a directory entry for the new directory in this directory */

  ret = fat_allocatedirentry(fs, &dirinfo);
  if (ret != OK)
    {
      goto errout_with_lock;
    }

  parentsector = fs->fs_currentsector;

  /* Allocate a cluster for new directory */

  dircluster = fat_createchain(fs);
  if (dircluster < 0)
    {
      ret = dircluster;
      goto errout_with_lock;
    }
  else if (dircluster < 2)
    {
      ret = -ENOSPC;
      goto errout_with_lock;
    }

  dirsector = fat_cluster2sector(fs, dircluster);
  if (dirsector < 0)
    {
      ret = dirsector;
      goto errout_with_lock;
    }

  /* Flush any existing, dirty data in fs_buffer (because we need
   * it to create the directory entries.
   */

  ret = fat_fscacheflush(fs);
  if (ret < 0)
    {
      goto errout_with_lock;
    }

  /* Get a pointer to the first directory entry in the sector */

  direntry = fs->fs_buffer;

  /* Now erase the contents of fs_buffer */

  fs->fs_currentsector = dirsector;
  memset(direntry, 0, fs->fs_hwsectorsize);

  /* Now clear all sectors in the new directory cluster (except for the
   * first).
   */

  for (i = 1; i < fs->fs_fatsecperclus; i++)
    {
      ret = fat_hwwrite(fs, direntry, ++dirsector, 1);
      if (ret < 0)
        {
          goto errout_with_lock;
        }
    }

  /* Now create the "." directory entry in the first directory slot.  These
   * are special directory entries and are not handled by the normal
   * directory management routines.
   */

  memset(&direntry[DIR_NAME], ' ', DIR_MAXFNAME);
  direntry[DIR_NAME] = '.';
  DIR_PUTATTRIBUTES(direntry, FATATTR_DIRECTORY);

  crtime = fat_systime2fattime();
  DIR_PUTCRTIME(direntry, crtime & 0xffff);
  DIR_PUTWRTTIME(direntry, crtime & 0xffff);
  DIR_PUTCRDATE(direntry, crtime >> 16);
  DIR_PUTWRTDATE(direntry, crtime >> 16);

  /* Create ".." directory entry in the second directory slot */

  direntry2 = direntry + DIR_SIZE;

  /* So far, the two entries are nearly the same */

  memcpy(direntry2, direntry, DIR_SIZE);
  direntry2[DIR_NAME + 1] = '.';

  /* Now add the cluster information to both directory entries */

  DIR_PUTFSTCLUSTHI(direntry, dircluster >> 16);
  DIR_PUTFSTCLUSTLO(direntry, dircluster);

  parentcluster = dirinfo.dir.fd_startcluster;
  if (parentcluster == fs->fs_rootbase)
    {
      parentcluster = 0;
    }

  DIR_PUTFSTCLUSTHI(direntry2, parentcluster >> 16);
  DIR_PUTFSTCLUSTLO(direntry2, parentcluster);

  /* Save the first sector of the directory cluster and re-read
   * the parentsector
   */

  fs->fs_dirty = true;
  ret = fat_fscacheread(fs, parentsector);
  if (ret < 0)
    {
      goto errout_with_lock;
    }

  /* Write the new entry directory entry in the parent directory */

  ret = fat_dirwrite(fs, &dirinfo, FATATTR_DIRECTORY, crtime);
  if (ret < 0)
    {
      goto errout_with_lock;
    }

  /* Set subdirectory start cluster. We assume that fat_dirwrite() did not
   * change the sector in the cache.
   */

  direntry = &fs->fs_buffer[dirinfo.fd_seq.ds_offset];
  DIR_PUTFSTCLUSTLO(direntry, dircluster);
  DIR_PUTFSTCLUSTHI(direntry, dircluster >> 16);
  fs->fs_dirty = true;

  /* Now update the FAT32 FSINFO sector */

  ret = fat_updatefsinfo(fs);
  if (ret < 0)
    {
      goto errout_with_lock;
    }

  nxmutex_unlock(&fs->fs_lock);
  return OK;

errout_with_lock:
  nxmutex_unlock(&fs->fs_lock);
  return ret;

#endif
}
static int fat_rmdir(FAR struct inode *mountpt, FAR const char *relpath)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)mountpt; (void)relpath; 
  return -EROFS;
#else

  FAR struct fat_mountpt_s *fs;
  int ret;

  /* Sanity checks */

  DEBUGASSERT(mountpt && mountpt->i_private);

  /* Get the mountpoint private data from the inode structure */

  fs = mountpt->i_private;

  /* Check if the mount is still healthy */

  ret = nxmutex_lock(&fs->fs_lock);
  if (ret < 0)
    {
      return ret;
    }

  ret = fat_checkmount(fs);
  if (ret == OK)
    {
      /* If the directory is open, the correct behavior is to remove the
       * directory name, but to keep the directory cluster chain in place
       * until the last open reference to the directory is closed.
       */

      /* Remove the directory.
       *
       * TODO: Need to defer deleting cluster chain if the file is open.
       */

      ret = fat_remove(fs, relpath, true);
    }

  nxmutex_unlock(&fs->fs_lock);
  return ret;

#endif
}
static int fat_rename(FAR struct inode *mountpt, FAR const char *oldrelpath,
                      FAR const char *newrelpath)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)mountpt; (void)oldrelpath; (void)newrelpath; 
  return -EROFS;
#else

  FAR struct fat_mountpt_s *fs;
  FAR struct fat_dirinfo_s dirinfo;
  FAR struct fat_dirseq_s dirseq;
  uint8_t *direntry;
  uint8_t dirstate[DIR_SIZE - DIR_ATTRIBUTES];
  int ret;

  /* Sanity checks */

  DEBUGASSERT(mountpt && mountpt->i_private);

  /* Get the mountpoint private data from the inode structure */

  fs = mountpt->i_private;

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

  /* Find the directory entry for the oldrelpath (there may be multiple
   * directory entries if long file name support is enabled).
   */

  ret = fat_finddirentry(fs, &dirinfo, oldrelpath);
  if (ret != OK)
    {
      /* Some error occurred -- probably -ENOENT */

      goto errout_with_lock;
    }

  /* One more check:  Make sure that the oldrelpath does not refer to the
   * root directory.  We can't rename the root directory.
   */

  if (dirinfo.fd_root)
    {
      ret = -EXDEV;
      goto errout_with_lock;
    }

  /* Save the information that will need to recover the directory sector and
   * directory entry offset to the old directory.
   *
   * Save the positional information of the old directory entry.
   */

  memcpy(&dirseq, &dirinfo.fd_seq, sizeof(struct fat_dirseq_s));

  /* Save the non-name-related portion of the directory entry intact */

  direntry = &fs->fs_buffer[dirinfo.fd_seq.ds_offset];
  memcpy(dirstate, &direntry[DIR_ATTRIBUTES], DIR_SIZE - DIR_ATTRIBUTES);

  /* Now find the directory where we should create the newpath object */

  ret = fat_finddirentry(fs, &dirinfo, newrelpath);

  /* What we expect is -ENOENT mean that the full directory path was
   * followed but that the object does not exists in the terminal directory.
   */

  if (ret != -ENOENT)
    {
      if (ret == OK)
        {
          /* It is an error if the directory entry at newrelpath already
           * exists.  The necessary steps to avoid this case should have
           * been handled by higher level logic in the VFS.
           */

          ret = -EEXIST;
        }

      goto errout_with_lock;
    }

  /* Reserve a directory entry. If long file name support is enabled, then
   * this might, in fact, allocate a sequence of directory entries.  A side
   * effect of fat_allocatedirentry() in either case is that it leaves the
   * short file name entry in the sector cache.
   */

  ret = fat_allocatedirentry(fs, &dirinfo);
  if (ret != OK)
    {
      goto errout_with_lock;
    }

  /* Then write the new file name into the directory entry.  This, of course,
   * may involve writing multiple directory entries if long file name
   * support is enabled.  A side effect of fat_allocatedirentry() in either
   * case is that it leaves the short file name entry in the sector cache.
   */

  ret = fat_dirnamewrite(fs, &dirinfo);
  if (ret < 0)
    {
      goto errout_with_lock;
    }

  /* Copy the unchanged information into the new short file name entry. */

  direntry = &fs->fs_buffer[dirinfo.fd_seq.ds_offset];
  memcpy(&direntry[DIR_ATTRIBUTES], dirstate, DIR_SIZE - DIR_ATTRIBUTES);
  fs->fs_dirty = true;

  /* Remove the old entry, flushing the new directory entry to disk.  If
   * the old file name was a long file name, then multiple directory
   * entries may be freed.
   */

  ret = fat_freedirentry(fs, &dirseq);
  if (ret < 0)
    {
      goto errout_with_lock;
    }

  /* Write the old entry to disk and update FSINFO if necessary */

  ret = fat_updatefsinfo(fs);
  if (ret < 0)
    {
      goto errout_with_lock;
    }

  nxmutex_unlock(&fs->fs_lock);
  return OK;

errout_with_lock:
  nxmutex_unlock(&fs->fs_lock);
  return ret;

#endif
}
static int fat_zero_cluster(FAR struct fat_mountpt_s *fs, int cluster,
                            int start, int end)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)cluster; (void)start; (void)end; 
  return -EROFS;
#else

  FAR uint8_t *buf;
  int zero_len = fs->fs_hwsectorsize - (start & (fs->fs_hwsectorsize - 1));
  off_t i;
  off_t sector = fat_cluster2sector(fs, cluster);
  off_t start_sec = sector + start / fs->fs_hwsectorsize;
  off_t end_sec = sector + DIV_ROUND_UP(end, fs->fs_hwsectorsize);
  int ret;

  buf = lib_get_tempbuffer(fs->fs_hwsectorsize);
  if (!buf)
    {
      return -ENOMEM;
    }

  if (zero_len)
    {
      ret = fat_hwread(fs, buf, start_sec, 1);
      if (ret < 0)
        {
          goto out;
        }

      memset(buf + fs->fs_hwsectorsize - zero_len, 0, zero_len);

      ret = fat_hwwrite(fs, buf, start_sec, 1);
      if (ret < 0)
        {
          goto out;
        }

      start_sec++;
    }

  memset(buf, 0, fs->fs_hwsectorsize - zero_len);

  for (i = start_sec; i < end_sec; i++)
    {
      ret = fat_hwwrite(fs, buf, i, 1);
      if (ret < 0)
        {
          goto out;
        }
    }

  ret = OK;

out:
  lib_put_tempbuffer(buf);

  return ret;

#endif
}
int fat_putcluster(struct fat_mountpt_s *fs, uint32_t clusterno,
                   off_t nextcluster)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)clusterno; (void)nextcluster; 
  return -EROFS;
#else

  /* Verify that the cluster number is within range.  Zero erases the
   * cluster.
   */

  if (clusterno == 0 || (clusterno >= 2 && clusterno < fs->fs_nclusters + 2))
    {
      /* Okay.. Write the next cluster into the FAT.  The way we will do
       * this depends on the type of FAT filesystem we are dealing with.
       */

      switch (fs->fs_type)
        {
          case FSTYPE_FAT12 :
            {
              off_t        fatsector;
              unsigned int fatoffset;
              unsigned int fatindex;
              uint8_t      value;

              /* FAT12 is more complex because it has 12-bits (1.5 bytes)
               * per FAT entry. Get the offset to the first byte:
               */

              fatoffset = (clusterno * 3) / 2;
              fatsector = fs->fs_fatbase + SEC_NSECTORS(fs, fatoffset);

              /* Make sure that the sector at this offset is in the cache */

              if (fat_fscacheread(fs, fatsector) < 0)
                {
                  /* Read error */

                  break;
                }

              /* Get the LS byte first handling the 12-bit alignment within
               * the 16-bits
               */

              fatindex = fatoffset & SEC_NDXMASK(fs);
              if ((clusterno & 1) != 0)
                {
                  /* Save the LS four bits of the next cluster */

                  value = (fs->fs_buffer[fatindex] & 0x0f) |
                           (uint8_t)nextcluster << 4;
                }
              else
                {
                  /* Save the LS eight bits of the next cluster */

                  value = (uint8_t)nextcluster;
                }

              fs->fs_buffer[fatindex] = value;

              /* With FAT12, the second byte of the cluster number may lie in
               * a different sector than the first byte.
               */

              fatindex++;
              if (fatindex >= fs->fs_hwsectorsize)
                {
                  /* Read the next sector */

                  fatsector++;
                  fatindex = 0;

                  /* Set the dirty flag to make sure the sector that we
                   * just modified is written out.
                   */

                  fs->fs_dirty = true;
                  if (fat_fscacheread(fs, fatsector) < 0)
                    {
                      /* Read error */

                      break;
                    }
                }

              /* Output the MS byte first handling the 12-bit alignment
               * within the 16-bits
               */

              if ((clusterno & 1) != 0)
                {
                  /* Save the MS eight bits of the next cluster */

                  value = (uint8_t)(nextcluster >> 4);
                }
              else
                {
                  /* Save the MS four bits of the next cluster */

                  value = (fs->fs_buffer[fatindex] & 0xf0) |
                          ((nextcluster >> 8) & 0x0f);
                }

              fs->fs_buffer[fatindex] = value;
            }
          break;

          case FSTYPE_FAT16 :
            {
              unsigned int fatoffset = 2 * clusterno;
              off_t        fatsector = fs->fs_fatbase +
                                       SEC_NSECTORS(fs, fatoffset);
              unsigned int fatindex  = fatoffset & SEC_NDXMASK(fs);

              if (fat_fscacheread(fs, fatsector) < 0)
                {
                  /* Read error */

                  break;
                }

              FAT_PUTFAT16(fs->fs_buffer, fatindex, nextcluster & 0xffff);
            }
          break;

          case FSTYPE_FAT32 :
            {
              unsigned int fatoffset = 4 * clusterno;
              off_t        fatsector = fs->fs_fatbase +
                                       SEC_NSECTORS(fs, fatoffset);
              unsigned int fatindex  = fatoffset & SEC_NDXMASK(fs);
              uint32_t     val;

              if (fat_fscacheread(fs, fatsector) < 0)
                {
                  /* Read error */

                  break;
                }

              /* Keep the top 4 bits */

              val = FAT_GETFAT32(fs->fs_buffer, fatindex) & 0xf0000000;
              FAT_PUTFAT32(fs->fs_buffer, fatindex,
                           val | (nextcluster & 0x0fffffff));
            }
          break;

          default:
            return -EINVAL;
        }

      /* Mark the modified sector as "dirty" and return success */

      fs->fs_dirty = true;
      return OK;
    }

  return -EINVAL;

#endif
}
int fat_removechain(struct fat_mountpt_s *fs, uint32_t cluster)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)cluster; 
  return -EROFS;
#else

  int32_t nextcluster;
  int    ret;

  /* Loop while there are clusters in the chain */

  while (cluster >= 2 && cluster < fs->fs_nclusters + 2)
    {
      /* Get the next cluster after the current one */

      nextcluster = fat_getcluster(fs, cluster);
      if (nextcluster < 0)
        {
          /* Error! */

          return nextcluster;
        }

      /* Then nullify current cluster -- removing it from the chain */

      ret = fat_putcluster(fs, cluster, 0);
      if (ret < 0)
        {
          return ret;
        }

      /* Update FSINFINFO data */

      if (fs->fs_fsifreecount != 0xffffffff)
        {
          fs->fs_fsifreecount++;
          fs->fs_fsidirty = true;
        }

      /* Then set up to remove the next cluster */

      cluster = nextcluster;
    }

  return OK;

#endif
}
int32_t fat_extendchain(struct fat_mountpt_s *fs, uint32_t cluster)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)cluster; 
  return -EROFS;
#else

  off_t    startsector;
  uint32_t newcluster;
  uint32_t startcluster;
  int      ret;

  /* The special value 0 is used when the new chain should start */

  if (cluster == 0)
    {
      /* The FSINFO NextFree entry should be a good starting point
       * in the search for a new cluster
       */

      startcluster = fs->fs_fsinextfree;
      if (startcluster == 0 || startcluster >= fs->fs_nclusters + 2)
        {
          /* But it is bad.. we have to start at the beginning */

          startcluster = 1;
        }
    }
  else
    {
      /* We are extending an existing chain. Verify that this
       * is a valid cluster by examining its start sector.
       */

      startsector = fat_getcluster(fs, cluster);
      if (startsector < 0)
        {
          /* An error occurred, return the error value */

          return startsector;
        }
      else if (startsector < 2)
        {
          /* Oops.. this cluster does not exist. */

          return 0;
        }
      else if (startsector < fs->fs_nclusters + 2)
        {
          /* It is already followed by next cluster */

          return startsector;
        }

      /* Okay.. it checks out */

      startcluster = cluster;
    }

  /* Loop until (1) we discover that there are not free clusters
   * (return 0), an errors occurs (return -errno), or (3) we find
   * the next cluster (return the new cluster number).
   */

  newcluster = startcluster;
  for (; ; )
    {
      /* Examine the next cluster in the FAT */

      newcluster++;
      if (newcluster >= fs->fs_nclusters + 2)
        {
          /* If we hit the end of the available clusters, then
           * wrap back to the beginning because we might have
           * started at a non-optimal place.  But don't continue
           * past the start cluster.
           */

          newcluster = 2;
          if (newcluster > startcluster)
            {
              /* We are back past the starting cluster, then there
               * is no free cluster.
               */

              return 0;
            }
        }

      /* We have a candidate cluster.  Check if the cluster number is
       * mapped to a group of sectors.
       */

      startsector = fat_getcluster(fs, newcluster);
      if (startsector == 0)
        {
          /* Found have found a free cluster break out */

          break;
        }
      else if (startsector < 0)
        {
          /* Some error occurred, return the error number */

          return startsector;
        }

      /* We wrap all the back to the starting cluster?  If so, then
       * there are no free clusters.
       */

      if (newcluster == startcluster)
        {
          return 0;
        }
    }

  /* We get here only if we break out with an available cluster
   * number in 'newcluster'  Now mark that cluster as in-use.
   */

  ret = fat_putcluster(fs, newcluster, 0x0fffffff);
  if (ret < 0)
    {
      /* An error occurred */

      return ret;
    }

  /* And link if to the start cluster (if any) */

  if (cluster)
    {
      /* There is a start cluster -- link it */

      ret = fat_putcluster(fs, cluster, newcluster);
      if (ret < 0)
        {
          return ret;
        }
    }

  /* And update the FINSINFO for the next time we have to search */

  fs->fs_fsinextfree = newcluster;
  if (fs->fs_fsifreecount != 0xffffffff)
    {
      fs->fs_fsifreecount--;
      fs->fs_fsidirty = true;
    }

  /* Return then number of the new cluster that was added to the chain */

  return newcluster;

#endif
}
int fat_dirtruncate(struct fat_mountpt_s *fs, FAR uint8_t *direntry)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)direntry; 
  return -EROFS;
#else

  unsigned int startcluster;
  uint32_t writetime;
  off_t savesector;
  int ret;

  /* Get start cluster of the file to truncate */

  startcluster = ((uint32_t)DIR_GETFSTCLUSTHI(direntry) << 16) |
                  DIR_GETFSTCLUSTLO(direntry);

  /* Clear the cluster start value in the directory and set the file size
   * to zero.  This makes the file look empty but also have to dispose of
   * all of the clusters in the chain.
   */

  DIR_PUTFSTCLUSTHI(direntry, 0);
  DIR_PUTFSTCLUSTLO(direntry, 0);
  DIR_PUTFILESIZE(direntry, 0);

  /* Set the ARCHIVE attribute and update the write time */

  DIR_PUTATTRIBUTES(direntry, FATATTR_ARCHIVE);

  writetime = fat_systime2fattime();
  DIR_PUTWRTTIME(direntry, writetime & 0xffff);
  DIR_PUTWRTDATE(direntry, writetime >> 16);

  /* This sector needs to be written back to disk eventually */

  fs->fs_dirty = true;

  /* Now remove the entire cluster chain comprising the file */

  savesector = fs->fs_currentsector;
  ret = fat_removechain(fs, startcluster);
  if (ret < 0)
    {
      return ret;
    }

  /* Setup FSINFO to reuse the old start cluster next */

  fs->fs_fsinextfree = startcluster - 1;

  /* Make sure that the directory is still in the cache */

  return fat_fscacheread(fs, savesector);

#endif
}
int fat_dirshrink(struct fat_mountpt_s *fs, FAR uint8_t *direntry,
                  off_t length)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)direntry; (void)length; 
  return -EROFS;
#else

  off_t clustersize;
  off_t remaining;
  uint32_t writetime;
  int32_t lastcluster;
  int32_t cluster;
  int ret;

  /* Get start cluster of the file to truncate */

  lastcluster = ((uint32_t)DIR_GETFSTCLUSTHI(direntry) << 16) |
                 DIR_GETFSTCLUSTLO(direntry);

  /* Set the file size to the new length.  */

  DIR_PUTFILESIZE(direntry, length);

  /* Set the ARCHIVE attribute and update the write time */

  DIR_PUTATTRIBUTES(direntry, FATATTR_ARCHIVE);

  writetime = fat_systime2fattime();
  DIR_PUTWRTTIME(direntry, writetime & 0xffff);
  DIR_PUTWRTDATE(direntry, writetime >> 16);

  /* This sector needs to be written back to disk eventually */

  fs->fs_dirty = true;

  /* Now find the cluster change to be removed.  Start with the cluster
   * after the current one (which we know contains data).
   */

  cluster = fat_getcluster(fs, lastcluster);
  if (cluster < 0)
    {
      return cluster;
    }

  clustersize = fs->fs_fatsecperclus * fs->fs_hwsectorsize;
  remaining   = length;

  while (cluster >= 2 && cluster < fs->fs_nclusters + 2)
    {
      /* Will there be data in the next cluster after the shrinkage? */

      if (remaining <= clustersize)
        {
          /* No.. then nullify next cluster -- removing it from the
           * chain.
           */

          ret = fat_putcluster(fs, lastcluster, 0);
          if (ret < 0)
            {
              return ret;
            }

          /* Then free the remainder of the chain */

          ret = fat_removechain(fs, cluster);
          if (ret < 0)
            {
              return ret;
            }

          /* Setup FSINFO to reuse the removed cluster next */

          fs->fs_fsinextfree = cluster - 1;
          break;
        }

      /* Then set up to remove the next cluster */

      lastcluster = cluster;
      cluster     = fat_getcluster(fs, cluster);

      if (cluster < 0)
        {
          return cluster;
        }

      remaining  -= clustersize;
    }

  return OK;

#endif
}
int fat_dirextend(FAR struct fat_mountpt_s *fs, FAR struct fat_file_s *ff,
                  off_t length)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)ff; (void)length; 
  return -EROFS;
#else

  int32_t cluster;
  off_t remaining;
  off_t pos;
  unsigned int zerosize;
  int sectndx;
  int ret;

  /* We are extending the file.  This is essentially the same as a write
   * except that (1) we write zeros and (2) we don't update the file
   * position.
   */

  pos = ff->ff_size;

  /* Get the first sector to write to. */

  if (!ff->ff_currentsector)
    {
      /* Has the starting cluster been defined? */

      if (ff->ff_startcluster == 0)
        {
          /* No.. we have to create a new cluster chain */

          ff->ff_startcluster     = fat_createchain(fs);
          ff->ff_currentcluster   = ff->ff_startcluster;
          ff->ff_sectorsincluster = fs->fs_fatsecperclus;
        }

      /* The current sector can then be determined from the current cluster
       * and the file offset.
       */

      ret = fat_currentsector(fs, ff, pos);
      if (ret < 0)
        {
          return ret;
        }
    }

  /* Loop until either (1) the file has been fully extended with zeroed data
   * or (2) an error occurs.  We assume we start with the current sector in
   * cache (ff_currentsector)
   */

  sectndx   = pos & SEC_NDXMASK(fs);
  remaining = length - pos;

  while (remaining > 0)
    {
      /* Check if the current write stream has incremented to the next
       * cluster boundary
       */

      if (ff->ff_sectorsincluster < 1)
        {
          /* Extend the current cluster by one (unless lseek was used to
           * move the file position back from the end of the file)
           */

          cluster = fat_extendchain(fs, ff->ff_currentcluster);

          /* Verify the cluster number */

          if (cluster < 0)
            {
              return (int)cluster;
            }
          else if (cluster < 2 || cluster >= fs->fs_nclusters + 2)
            {
              return -ENOSPC;
            }

          /* Setup to zero the first sector from the new cluster */

          ff->ff_currentcluster   = cluster;
          ff->ff_sectorsincluster = fs->fs_fatsecperclus;
          ff->ff_currentsector    = fat_cluster2sector(fs, cluster);
        }

      /* Decide whether we are performing a read-modify-write
       * operation, in which case we have to read the existing sector
       * into the buffer first.
       *
       * There are two cases where we can avoid this read:
       *
       * - If we are performing a whole-sector clear that was rejected
       *   by fat_hwwrite(), i.e. sectndx == 0 and remaining >= sector size.
       *
       * - If the clear is aligned to the beginning of the sector and
       *   extends beyond the end of the file, i.e. sectndx == 0 and
       *   file pos + remaining >= file size.
       */

      if (sectndx == 0 && (remaining >= fs->fs_hwsectorsize ||
          (pos + remaining) >= ff->ff_size))
        {
          /* Flush unwritten data in the sector cache. */

          ret = fat_ffcacheflush(fs, ff);
          if (ret < 0)
            {
              return ret;
            }

          /* Now mark the clean cache buffer as the current sector. */

          ff->ff_cachesector = ff->ff_currentsector;
        }
      else
        {
          /* Read the current sector into memory (perhaps first flushing the
           * old, dirty sector to disk).
           */

          ret = fat_ffcacheread(fs, ff, ff->ff_currentsector);
          if (ret < 0)
            {
              return ret;
            }
        }

      /* Copy the requested part of the sector from the user buffer */

      zerosize = fs->fs_hwsectorsize - sectndx;
      if (zerosize > remaining)
        {
          /* We will not zero to the end of the sector. */

          zerosize = remaining;
        }
      else
        {
          /* We will zero to the end of the buffer (or beyond).  Bump up
           * the current sector number (actually the next sector number).
           */

          ff->ff_sectorsincluster--;
          ff->ff_currentsector++;
        }

      /* Zero the data into the cached sector and make sure that the cached
       * sector is marked "dirty" so that it will be written back.
       */

      memset(&ff->ff_buffer[sectndx], 0, zerosize);
      ff->ff_bflags |= (FFBUFF_DIRTY | FFBUFF_VALID | FFBUFF_MODIFIED);

      /* Set up for the next sector */

      pos       += zerosize;
      remaining -= zerosize;
      sectndx    = pos & SEC_NDXMASK(fs);
    }

  /* The truncation has completed without error.  Update the file size */

  ff->ff_size = length;
  return OK;

#endif
}
int fat_allocatedirentry(FAR struct fat_mountpt_s *fs,
                         FAR struct fat_dirinfo_s *dirinfo)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)dirinfo; 
  return -EROFS;
#else

  int32_t cluster;
  int32_t prevcluster;
  off_t   sector;
  int     ret;
  int     i;

  /* Re-initialize directory object */

  cluster = dirinfo->dir.fd_startcluster;

  /* Loop until we successfully allocate the sequence of directory entries
   * or until to fail to extend the directory cluster chain.
   */

  for (; ; )
    {
      /* Can this cluster chain be extended */

      if (cluster)
        {
          /* Cluster chain can be extended */

          dirinfo->dir.fd_currcluster = cluster;
          dirinfo->dir.fd_currsector  = fat_cluster2sector(fs, cluster);
        }
      else
        {
          /* Fixed size FAT12/16 root directory is at fixed offset/size */

          dirinfo->dir.fd_currsector = fs->fs_rootbase;
        }

      /* Start at the first entry in the root directory. */

      dirinfo->dir.fd_index = 0;

      /* Is this a path segment a long or a short file.  Was a long file
       * name parsed?
       */

#ifdef CONFIG_FAT_LFN
      if (dirinfo->fd_lfname[0] != '\0')
        {
          /* Yes.. Allocate for the sequence of long file name directory
           * entries plus a short file name directory entry.
           */

          ret = fat_allocatelfnentry(fs, dirinfo);
        }

      /* No.. Allocate only a short file name directory entry */

      else
#endif
        {
          ret = fat_allocatesfnentry(fs, dirinfo);
        }

      /* Did we successfully allocate the directory entries?  If the error
       * value is -ENOSPC, then we can try to extend the directory cluster
       * (we can't handle other return values)
       */

      if (ret == OK || ret != -ENOSPC)
        {
          return ret;
        }

      /* If we get here, then we have reached the end of the directory table
       * in this sector without finding a free directory entry.
       *
       * It this is a fixed size directory entry, then this is an error.
       * Otherwise, we can try to extend the directory cluster chain to
       * make space for the new directory entry.
       */

      if (!cluster)
        {
          /* The size is fixed */

          return -ENOSPC;
        }

      /* Try to extend the cluster chain for this directory */

      prevcluster = cluster;
      cluster     = fat_extendchain(fs, dirinfo->dir.fd_currcluster);

      if (cluster < 0)
        {
          return cluster;
        }

      /* Flush out any cached data in fs_buffer.. we are going to use
       * it to initialize the new directory cluster.
       */

      ret = fat_fscacheflush(fs);
      if (ret < 0)
        {
          return ret;
        }

      /* Clear all sectors comprising the new directory cluster */

      fs->fs_currentsector = fat_cluster2sector(fs, cluster);
      memset(fs->fs_buffer, 0, fs->fs_hwsectorsize);

      sector = fs->fs_currentsector;
      for (i = fs->fs_fatsecperclus; i; i--)
        {
          ret = fat_hwwrite(fs, fs->fs_buffer, sector, 1);
          if (ret < 0)
            {
              return ret;
            }

          sector++;
        }

      /* Start the search again */

      cluster = prevcluster;
    }

#endif
}
int fat_freedirentry(FAR struct fat_mountpt_s *fs, struct fat_dirseq_s *seq)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)seq; 
  return -EROFS;
#else

#ifdef CONFIG_FAT_LFN
  struct fs_fatdir_s dir;
  FAR uint8_t *direntry;
  uint16_t diroffset;
  off_t startsector;
  int ret;

  /* Set it to the cluster containing the "last" LFN entry (that appears
   * first on the media).
   */

  dir.fd_currcluster = seq->ds_lfncluster;
  dir.fd_currsector  = seq->ds_lfnsector;
  dir.fd_index       = seq->ds_lfnoffset / DIR_SIZE;

  /* Remember that ds_lfnoffset is the offset in the sector and not the
   * cluster.
   */

  startsector        = fat_cluster2sector(fs, dir.fd_currcluster);
  dir.fd_index      += (dir.fd_currsector - startsector) * DIRSEC_NDIRS(fs);

  /* Free all of the directory entries used for the sequence of long file
   * name and for the single short file name entry.
   */

  for (; ; )
    {
      /* Read the directory sector into the sector cache */

      ret = fat_fscacheread(fs, dir.fd_currsector);
      if (ret < 0)
        {
          return ret;
        }

      /* Get a pointer to the directory entry */

      diroffset = (dir.fd_index & DIRSEC_NDXMASK(fs)) * DIR_SIZE;
      direntry  = &fs->fs_buffer[diroffset];

      /* Then mark the entry as deleted */

      direntry[DIR_NAME] = DIR0_EMPTY;
      fs->fs_dirty       = true;

      /* Did we just free the single short file name entry? */

      if (dir.fd_currsector == seq->ds_sector &&
          diroffset == seq->ds_offset)
        {
          /* Yes.. then we are finished. flush anything remaining in the
           * cache and return, probably successfully.
           */

          return fat_fscacheflush(fs);
        }

      /* There are more entries to go.. Try the next directory entry */

      ret = fat_nextdirentry(fs, &dir);
      if (ret < 0)
        {
          return ret;
        }
    }

#else
  FAR uint8_t *direntry;
  int ret;

  /* Free the single short file name entry.
   *
   * Make sure that the sector containing the directory entry is in the
   * cache.
   */

  ret = fat_fscacheread(fs, seq->ds_sector);
  if (ret == OK)
    {
      /* Then mark the entry as deleted */

      direntry           = &fs->fs_buffer[seq->ds_offset];
      direntry[DIR_NAME] = DIR0_EMPTY;
      fs->fs_dirty       = true;
    }

  return ret;
#endif

#endif
}
int fat_dirnamewrite(FAR struct fat_mountpt_s *fs,
                     FAR struct fat_dirinfo_s *dirinfo)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)dirinfo; 
  return -EROFS;
#else

#ifdef CONFIG_FAT_LFN
  int ret;

  /* Is this a long file name? */

  if (dirinfo->fd_lfname[0] != '\0')
    {
      /* Write the sequence of long file name directory entries (this
       * function also creates the short file name alias).
       */

      ret = fat_putlfname(fs, dirinfo);
      if (ret != OK)
        {
          return ret;
        }
    }

  /* On return, fat_lfsfname() will leave the short file name entry in the
   * cache.  So we can just fall through to write that directory entry,
   * perhaps using the short file name alias for the long file name.
   */

#endif

  return fat_putsfname(fs, dirinfo);

#endif
}
int fat_dirwrite(FAR struct fat_mountpt_s *fs,
                 FAR struct fat_dirinfo_s *dirinfo,
                 uint8_t attributes, uint32_t fattime)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)dirinfo; (void)attributes; (void)fattime; 
  return -EROFS;
#else

#ifdef CONFIG_FAT_LFN
  int ret;

  /* Does this directory entry have a long file name? */

  if (dirinfo->fd_lfname[0] != '\0')
    {
      /* Write the sequence of long file name directory entries (this
       * function also creates the short file name alias).
       */

      ret = fat_putlfname(fs, dirinfo);
      if (ret != OK)
        {
          return ret;
        }
    }

  /* On return, fat_lfsfname() will leave the short file name entry in the
   * cache.  So we can just fall through to write that directory entry,
   * perhaps using the short file name alias for the long file name.
   */

#endif

  /* Put the short file name entry data */

  return fat_putsfdirentry(fs, dirinfo, attributes, fattime);

#endif
}
int fat_dircreate(FAR struct fat_mountpt_s *fs,
                  FAR struct fat_dirinfo_s *dirinfo)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)dirinfo; 
  return -EROFS;
#else

  uint32_t fattime;
  int ret;

  /* Allocate a directory entry.  If long file name support is enabled, then
   * this might, in fact, allocate a sequence of directory entries.
   */

  ret = fat_allocatedirentry(fs, dirinfo);
  if (ret != OK)
    {
      /* Failed to allocate the required directory entry or entries. */

      return ret;
    }

  /* Write the directory entry (or entries) with the current time and the
   * ARCHIVE attribute.
   */

  fattime = fat_systime2fattime();
  return fat_dirwrite(fs, dirinfo, FATATTR_ARCHIVE, fattime);

#endif
}
int fat_remove(FAR struct fat_mountpt_s *fs, FAR const char *relpath,
               bool directory)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)fs; (void)relpath; (void)directory; 
  return -EROFS;
#else

  struct fat_dirinfo_s dirinfo;
  uint32_t             dircluster;
  FAR uint8_t         *direntry;
  int                  ret;

  /* Find the directory entry referring to the entry to be deleted */

  ret = fat_finddirentry(fs, &dirinfo, relpath);
  if (ret != OK)
    {
      /* Most likely, some element of the path does not exist. */

      return -ENOENT;
    }

  /* Check if this is a FAT12/16 root directory */

  if (dirinfo.fd_root)
    {
      /* The root directory cannot be removed */

      return -EPERM;
    }

  /* The object has to have write access to be deleted */

  direntry = &fs->fs_buffer[dirinfo.fd_seq.ds_offset];
  if ((DIR_GETATTRIBUTES(direntry) & FATATTR_READONLY) != 0)
    {
      /* It is a read-only entry */

      return -EACCES;
    }

  /* Get the directory sector and cluster containing the entry to be
   * deleted.
   */

  dircluster =
      ((uint32_t)DIR_GETFSTCLUSTHI(direntry) << 16) |
      DIR_GETFSTCLUSTLO(direntry);

  /* Is this entry a directory? */

  if (DIR_GETATTRIBUTES(direntry) & FATATTR_DIRECTORY)
    {
      /* It is a sub-directory. Check if we are be asked to remove
       * a directory or a file.
       */

      if (!directory)
        {
          /* We are asked to delete a file */

          return -EISDIR;
        }

      /* We are asked to delete a directory. Check if this sub-directory is
       * empty (i.e., that there are no valid entries other than the initial
       * '.' and '..' entries).
       */

      dirinfo.dir.fd_currcluster = dircluster;
      dirinfo.dir.fd_currsector  = fat_cluster2sector(fs, dircluster);
      dirinfo.dir.fd_index       = 2;

      /* Loop until either (1) an entry is found in the directory (error),
       * (2) the directory is found to be empty, or (3) some error occurs.
       */

      for (; ; )
        {
          unsigned int subdirindex;
          uint8_t     *subdirentry;

          /* Make sure that the sector containing the of the subdirectory
           * sector is in the cache
           */

          ret = fat_fscacheread(fs, dirinfo.dir.fd_currsector);
          if (ret < 0)
            {
              return ret;
            }

          /* Get a reference to the next entry in the directory */

          subdirindex = (dirinfo.dir.fd_index & DIRSEC_NDXMASK(fs)) *
                        DIR_SIZE;
          subdirentry = &fs->fs_buffer[subdirindex];

          /* Is this the last entry in the directory? */

          if (subdirentry[DIR_NAME] == DIR0_ALLEMPTY)
            {
              /* Yes then the directory is empty.  Break out of the
               * loop and delete the directory.
               */

              break;
            }

          /* Check if the next entry refers to a file or directory */

          if (subdirentry[DIR_NAME] != DIR0_EMPTY &&
              !(DIR_GETATTRIBUTES(subdirentry) & FATATTR_VOLUMEID))
            {
              /* The directory is not empty */

              return -ENOTEMPTY;
            }

          /* Get the next directory entry */

          ret = fat_nextdirentry(fs, &dirinfo.dir);
          if (ret < 0)
            {
              return ret;
            }
        }
    }
  else
    {
      /* It is a file. Check if we are be asked to remove a directory
       * or a file.
       */

      if (directory)
        {
          /* We are asked to remove a directory */

          return -ENOTDIR;
        }
    }

  /* Mark the directory entry 'deleted'.  If long file name support is
   * enabled, then multiple directory entries may be freed.
   */

  ret = fat_freedirentry(fs, &dirinfo.fd_seq);
  if (ret < 0)
    {
      return ret;
    }

  /* And remove the cluster chain making up the subdirectory */

  ret = fat_removechain(fs, dircluster);
  if (ret < 0)
    {
      return ret;
    }

  /* Update the FSINFO sector (FAT32) */

  ret = fat_updatefsinfo(fs);
  if (ret < 0)
    {
      return ret;
    }

  return OK;

#endif
}
int fat_setattrib(FAR const char *path, fat_attrib_t setbits,
                  fat_attrib_t clearbits)
{
#ifdef CONFIG_FAT_FORCE_READONLY
  (void)path; (void)setbits; (void)clearbits; 
  return -EROFS;
#else

  return fat_attrib(path, NULL, setbits, clearbits);

#endif
}
static int open_policy_fragment(int oflags){
#ifdef CONFIG_FAT_FORCE_READONLY
  if ((oflags & O_ACCMODE) != O_RDONLY ||
      (oflags & (O_CREAT | O_TRUNC | O_APPEND | O_EXCL)) != 0)
    {
      return -EROFS;
    }
#endif
return 0;}
int main(void){
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
 CHECK(fat_write(0,0,0)==-EROFS);
CHECK(fat_truncate(0,0)==-EROFS);
CHECK(fat_unlink(0,0)==-EROFS);
CHECK(fat_mkdir(0,0,0)==-EROFS);
CHECK(fat_rmdir(0,0)==-EROFS);
CHECK(fat_rename(0,0,0)==-EROFS);
CHECK(fat_zero_cluster(0,0,0,0)==-EROFS);
CHECK(fat_putcluster(0,0,0)==-EROFS);
CHECK(fat_removechain(0,0)==-EROFS);
CHECK(fat_extendchain(0,0)==-EROFS);
CHECK(fat_dirtruncate(0,0)==-EROFS);
CHECK(fat_dirshrink(0,0,0)==-EROFS);
CHECK(fat_dirextend(0,0,0)==-EROFS);
CHECK(fat_allocatedirentry(0,0)==-EROFS);
CHECK(fat_freedirentry(0,0)==-EROFS);
CHECK(fat_dirnamewrite(0,0)==-EROFS);
CHECK(fat_dirwrite(0,0,0,0)==-EROFS);
CHECK(fat_dircreate(0,0)==-EROFS);
CHECK(fat_remove(0,0,0)==-EROFS);
CHECK(fat_setattrib(0,0,0)==-EROFS);
 CHECK(fat_close(&file)==0 && !file.f_priv && !fs->fs_head);
 CHECK(fat_unbind(handle,&returned,0)==0 && returned==&block && opens==1 && closes==1);
 CHECK(writes==0 && allocs==frees);
 printf("PASS selected real FAT C branches: mount/read/cache/sync/close/unbind/mutator guards; reads=%u writes=%u allocs=%u frees=%u; boot+FSInfo validators mocked\n",reads,writes,allocs,frees);return 0;}
