#define CONFIG_USBHOST_MSC_READONLY 1
#include "mock-prefix.h"
static inline uint16_t usbhost_getle16(const uint8_t *val)
{
  return (uint16_t)val[1] << 8 | (uint16_t)val[0];
}

static inline uint16_t usbhost_getbe16(const uint8_t *val)
{
  return (uint16_t)val[0] << 8 | (uint16_t)val[1];
}

static inline uint32_t usbhost_getle32(const uint8_t *val)
{
  /* Little endian means LS halfword first in byte stream */

  return (uint32_t)usbhost_getle16(&val[2]) << 16 |
         (uint32_t)usbhost_getle16(val);
}

static inline uint32_t usbhost_getbe32(const uint8_t *val)
{
  /* Big endian means MS halfword first in byte stream */

  return (uint32_t)usbhost_getbe16(val) << 16 |
         (uint32_t)usbhost_getbe16(&val[2]);
}

static void usbhost_putle16(uint8_t *dest, uint16_t val)
{
  dest[0] = val & 0xff; /* Little endian means LS byte first in byte stream */
  dest[1] = val >> 8;
}

static void usbhost_putbe16(uint8_t *dest, uint16_t val)
{
  dest[0] = val >> 8; /* Big endian means MS byte first in byte stream */
  dest[1] = val & 0xff;
}

static void usbhost_putle32(uint8_t *dest, uint32_t val)
{
  /* Little endian means LS halfword first in byte stream */

  usbhost_putle16(dest, (uint16_t)(val & 0xffff));
  usbhost_putle16(dest + 2, (uint16_t)(val >> 16));
}

static void usbhost_putbe32(uint8_t *dest, uint32_t val)
{
  /* Big endian means MS halfword first in byte stream */

  usbhost_putbe16(dest, (uint16_t)(val >> 16));
  usbhost_putbe16(dest + 2, (uint16_t)(val & 0xffff));
}

static inline void usbhost_requestsensecbw(FAR struct usbmsc_cbw_s *cbw)
{
  FAR struct scsicmd_requestsense_s *reqsense;

  /* Format the CBW */

  usbhost_putle32(cbw->datlen, SCSIRESP_FIXEDSENSEDATA_SIZEOF);
  cbw->flags         = USBMSC_CBWFLAG_IN;
  cbw->cdblen        = SCSICMD_REQUESTSENSE_SIZEOF;

  /* Format the CDB */

  reqsense           = (FAR struct scsicmd_requestsense_s *)cbw->cdb;
  reqsense->opcode   = SCSI_CMD_REQUESTSENSE;
  reqsense->alloclen = SCSIRESP_FIXEDSENSEDATA_SIZEOF;

  usbhost_dumpcbw(cbw);
}

static inline void usbhost_testunitreadycbw(FAR struct usbmsc_cbw_s *cbw)
{
  /* Format the CBW */

  cbw->cdblen = SCSICMD_TESTUNITREADY_SIZEOF;

  /* Format the CDB */

  cbw->cdb[0] = SCSI_CMD_TESTUNITREADY;

  usbhost_dumpcbw(cbw);
}

static inline void usbhost_readcapacitycbw(FAR struct usbmsc_cbw_s *cbw)
{
  FAR struct scsicmd_readcapacity10_s *rcap10;

  /* Format the CBW */

  usbhost_putle32(cbw->datlen, SCSIRESP_READCAPACITY10_SIZEOF);
  cbw->flags     = USBMSC_CBWFLAG_IN;
  cbw->cdblen    = SCSICMD_READCAPACITY10_SIZEOF;

  /* Format the CDB */

  rcap10         = (FAR struct scsicmd_readcapacity10_s *)cbw->cdb;
  rcap10->opcode = SCSI_CMD_READCAPACITY10;

  usbhost_dumpcbw(cbw);
}

static inline void usbhost_inquirycbw (FAR struct usbmsc_cbw_s *cbw)
{
  FAR struct scscicmd_inquiry_s *inq;

  /* Format the CBW */

  usbhost_putle32(cbw->datlen, SCSIRESP_INQUIRY_SIZEOF);
  cbw->flags    = USBMSC_CBWFLAG_IN;
  cbw->cdblen   = SCSICMD_INQUIRY_SIZEOF;

  /* Format the CDB */

  inq           = (FAR struct scscicmd_inquiry_s *)cbw->cdb;
  inq->opcode   = SCSI_CMD_INQUIRY;
  usbhost_putbe16(inq->alloclen, SCSIRESP_INQUIRY_SIZEOF);

  usbhost_dumpcbw(cbw);
}

static inline void
usbhost_readcbw (blkcnt_t startsector, uint16_t blocksize,
                 unsigned int nsectors, FAR struct usbmsc_cbw_s *cbw)
{
  FAR struct scsicmd_read10_s *rd10;

  /* Format the CBW */

  usbhost_putle32(cbw->datlen, blocksize * nsectors);
  cbw->flags   = USBMSC_CBWFLAG_IN;
  cbw->cdblen  = SCSICMD_READ10_SIZEOF;

  /* Format the CDB */

  rd10 = (FAR struct scsicmd_read10_s *)cbw->cdb;
  rd10->opcode = SCSI_CMD_READ10;
  usbhost_putbe32(rd10->lba, startsector);
  usbhost_putbe16(rd10->xfrlen, nsectors);

  usbhost_dumpcbw(cbw);
}

static FAR struct usbmsc_cbw_s *
  usbhost_cbwalloc(FAR struct usbhost_state_s *priv)
{
  FAR struct usbmsc_cbw_s *cbw = NULL;

  DEBUGASSERT(priv->tbuffer && priv->tbuflen >= sizeof(struct usbmsc_cbw_s));

  /* Initialize the CBW structure */

  cbw = (FAR struct usbmsc_cbw_s *)priv->tbuffer;
  memset(cbw, 0, sizeof(struct usbmsc_cbw_s));
  usbhost_putle32(cbw->signature, USBMSC_CBW_SIGNATURE);
#ifdef CONFIG_USBHOST_MSC_READONLY
  usbhost_putle32(cbw->tag, ++priv->next_tag);
#endif
  return cbw;
}

static int usbhost_bot_failed(FAR struct usbhost_state_s *priv)
{
  priv->bot_failed = true;
  uerr("MSC checked BOT failed; re-enumeration required\n");
  return -EIO;
}

static int usbhost_checked_command(FAR struct usbhost_state_s *priv,
                                  FAR struct usbmsc_cbw_s *cbw,
                                  FAR uint8_t *data, size_t datalen,
                                  bool allow_not_ready)
{
  FAR struct usbhost_hubport_s *hport = priv->usbclass.hport;
  uint32_t tag;
  ssize_t nbytes;

  if (priv->disconnected || priv->bot_failed)
    {
      return -ENODEV;
    }

  /* cbw, data and the received CSW may share tbuffer. Save before IN. */

  tag = usbhost_getle32(cbw->tag);
  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                        (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
  if (nbytes != USBMSC_CBW_SIZEOF)
    {
      return usbhost_bot_failed(priv);
    }

  if (datalen != 0)
    {
      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin, data, datalen);
      if (nbytes != (ssize_t)datalen)
        {
          return usbhost_bot_failed(priv);
        }
    }

  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                        priv->tbuffer, USBMSC_CSW_SIZEOF);
  if (nbytes != USBMSC_CSW_SIZEOF ||
      usbhost_getle32(priv->tbuffer) != UINT32_C(0x53425355) ||
      usbhost_getle32(priv->tbuffer + 4) != tag ||
      usbhost_getle32(priv->tbuffer + 8) != 0 ||
      (priv->tbuffer[12] != 0 &&
       !(allow_not_ready && priv->tbuffer[12] == 1)))
    {
      return usbhost_bot_failed(priv);
    }

  return OK;
}

static int usbhost_checked_capacity(FAR struct usbhost_state_s *priv)
{
  FAR struct usbmsc_cbw_s *cbw;
  uint8_t response[8];
  uint32_t last;
  uint32_t blocksize;
  int ret;

  cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      return -ENOMEM;
    }

  usbhost_readcapacitycbw(cbw);
  /* xHCI's DMA bounce path handles this small caller-owned buffer. */

  ret = usbhost_checked_command(priv, cbw, response, sizeof(response), false);
  if (ret < 0)
    {
      return ret;
    }

  last = usbhost_getbe32(response);
  blocksize = usbhost_getbe32(response + 4);
  if (last == UINT32_MAX ||
      (blocksize != 512 && blocksize != 1024 &&
       blocksize != 2048 && blocksize != 4096))
    {
      return usbhost_bot_failed(priv);
    }

  priv->nblocks = last + 1;
  priv->blocksize = blocksize;
  return OK;
}

static ssize_t usbhost_checked_read(FAR struct inode *inode,
                                   FAR unsigned char *buffer,
                                   blkcnt_t startsector,
                                   unsigned int nsectors)
{
  FAR struct usbhost_state_s *priv = inode->i_private;
  FAR struct usbmsc_cbw_s *cbw;
  int ret = nxmutex_lock(&priv->lock);

  if (ret < 0)
    {
      return ret;
    }

  if (priv->disconnected || priv->bot_failed)
    {
      ret = -ENODEV;
    }
  else if (buffer == NULL || priv->blocksize == 0 ||
           startsector < 0 || (uint64_t)startsector > UINT32_MAX ||
           (uint64_t)startsector >= priv->nblocks || nsectors == 0 ||
           nsectors > UINT16_MAX ||
           nsectors > priv->nblocks - (uint64_t)startsector ||
           nsectors > 4096u / priv->blocksize)
    {
      ret = -EINVAL;
    }
  else
    {
      cbw = usbhost_cbwalloc(priv);
      if (!cbw)
        {
          ret = -ENOMEM;
        }
      else
        {
          usbhost_readcbw(startsector, priv->blocksize, nsectors, cbw);
          ret = usbhost_checked_command(priv, cbw, buffer,
                                        priv->blocksize * nsectors, false);
          if (ret == OK)
            {
              ret = nsectors;
            }
        }
    }

  nxmutex_unlock(&priv->lock);
  return ret;
}

static inline int usbhost_testunitready(FAR struct usbhost_state_s *priv)
{
#ifdef CONFIG_USBHOST_MSC_READONLY
  FAR struct usbmsc_cbw_s *cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      return -ENOMEM;
    }

  usbhost_testunitreadycbw(cbw);
  return usbhost_checked_command(priv, cbw, priv->tbuffer, 0, true);
#else

  FAR struct usbhost_hubport_s *hport;
  FAR struct usbmsc_cbw_s *cbw;
  ssize_t nbytes;

  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;

  /* Initialize a CBW (re-using the allocated transfer buffer) */

  cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      uerr("ERROR: Failed to create CBW\n");
      return -ENOMEM;
    }

  /* Construct and send the CBW */

  usbhost_testunitreadycbw(cbw);
  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                        (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
  if (nbytes >= 0)
    {
      /* Receive the CSW */

      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                             priv->tbuffer, USBMSC_CSW_SIZEOF);
      if (nbytes >= 0)
        {
          usbhost_dumpcsw((FAR struct usbmsc_csw_s *)priv->tbuffer);
        }
    }

  return nbytes < 0 ? (int)nbytes : OK;

#endif
}

static inline int usbhost_requestsense(FAR struct usbhost_state_s *priv)
{
#ifdef CONFIG_USBHOST_MSC_READONLY
  FAR struct usbmsc_cbw_s *cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      return -ENOMEM;
    }

  usbhost_requestsensecbw(cbw);
  return usbhost_checked_command(priv, cbw, priv->tbuffer, SCSIRESP_FIXEDSENSEDATA_SIZEOF, false);
#else

  FAR struct usbhost_hubport_s *hport;
  FAR struct usbmsc_cbw_s *cbw;
  ssize_t nbytes;

  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;

  /* Initialize a CBW (re-using the allocated transfer buffer) */

  cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      uerr("ERROR: Failed to create CBW\n");
      return -ENOMEM;
    }

  /* Construct and send the CBW */

  usbhost_requestsensecbw(cbw);
  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                        (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
  if (nbytes >= 0)
    {
      /* Receive the sense data response */

      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                             priv->tbuffer, SCSIRESP_FIXEDSENSEDATA_SIZEOF);
      if (nbytes >= 0)
        {
          /* Receive the CSW */

          nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                 priv->tbuffer, USBMSC_CSW_SIZEOF);
          if (nbytes >= 0)
            {
              usbhost_dumpcsw((FAR struct usbmsc_csw_s *)priv->tbuffer);
            }
        }
    }

  return nbytes < 0 ? (int)nbytes : OK;

#endif
}

static inline int usbhost_readcapacity(FAR struct usbhost_state_s *priv)
{
#ifdef CONFIG_USBHOST_MSC_READONLY
  return usbhost_checked_capacity(priv);
#else

  FAR struct usbhost_hubport_s *hport;
  FAR struct usbmsc_cbw_s *cbw;
  FAR struct scsiresp_readcapacity10_s *resp;
  ssize_t nbytes;

  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;

  /* Initialize a CBW (re-using the allocated transfer buffer) */

  cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      uerr("ERROR: Failed to create CBW\n");
      return -ENOMEM;
    }

  /* Construct and send the CBW */

  usbhost_readcapacitycbw(cbw);
  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                        (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
  if (nbytes >= 0)
    {
      /* Receive the read capacity CBW IN response */

      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                             priv->tbuffer, SCSIRESP_READCAPACITY10_SIZEOF);
      if (nbytes >= 0)
        {
          /* Save the capacity information */

          resp            = (FAR struct scsiresp_readcapacity10_s *)
                            priv->tbuffer;
          priv->nblocks   = usbhost_getbe32(resp->lba) + 1;
          priv->blocksize = usbhost_getbe32(resp->blklen);

          /* Receive the CSW */

          nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                 priv->tbuffer, USBMSC_CSW_SIZEOF);
          if (nbytes >= 0)
            {
              usbhost_dumpcsw((FAR struct usbmsc_csw_s *)priv->tbuffer);
            }
        }
    }

  return nbytes < 0 ? (int)nbytes : OK;

#endif
}

static inline int usbhost_inquiry(FAR struct usbhost_state_s *priv)
{
#ifdef CONFIG_USBHOST_MSC_READONLY
  FAR struct usbmsc_cbw_s *cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      return -ENOMEM;
    }

  usbhost_inquirycbw(cbw);
  return usbhost_checked_command(priv, cbw, priv->tbuffer, SCSIRESP_INQUIRY_SIZEOF, false);
#else

  FAR struct usbhost_hubport_s *hport;
  FAR struct usbmsc_cbw_s *cbw;
  ssize_t nbytes;

  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;

  /* Initialize a CBW (re-using the allocated transfer buffer) */

  cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      uerr("ERROR: Failed to create CBW\n");
      return -ENOMEM;
    }

  /* Construct and send the CBW */

  usbhost_inquirycbw(cbw);
  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                         (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
  if (nbytes >= 0)
    {
      /* Receive the CBW IN response */

      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                             priv->tbuffer, SCSIRESP_INQUIRY_SIZEOF);
      if (nbytes >= 0)
        {
#if 0
          FAR struct scsiresp_inquiry_s *resp;

          /* TODO: If USB debug is enabled, dump the response data here */

          resp = (FAR struct scsiresp_inquiry_s *)priv->tbuffer;
#endif
          /* Receive the CSW */

          nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                 priv->tbuffer, USBMSC_CSW_SIZEOF);
          if (nbytes >= 0)
            {
              usbhost_dumpcsw((FAR struct usbmsc_csw_s *)priv->tbuffer);
            }
        }
    }

  return nbytes < 0 ? (int)nbytes : OK;

#endif
}

static ssize_t usbhost_read(FAR struct inode *inode, unsigned char *buffer,
                            blkcnt_t startsector, unsigned int nsectors)
{
#ifdef CONFIG_USBHOST_MSC_READONLY
  return usbhost_checked_read(inode, buffer, startsector, nsectors);
#else

  FAR struct usbhost_state_s *priv;
  FAR struct usbhost_hubport_s *hport;
  ssize_t nbytes = 0;
  int ret;

  DEBUGASSERT(inode->i_private);
  priv = inode->i_private;

  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;

  uinfo("startsector: %" PRIuOFF " nsectors: %u "
        "sectorsize: %" PRIu16 "\n", startsector, nsectors, priv->blocksize);

  /* Check if the mass storage device is still connected */

  if (priv->disconnected)
    {
      /* No... the block driver is no longer bound to the class.  That means
       * that the USB storage device is no longer connected.  Refuse any
       * attempt to read from the device.
       */

      nbytes = -ENODEV;
    }
  else if (nsectors > 0)
    {
      FAR struct usbmsc_cbw_s *cbw;

      ret = nxmutex_lock(&priv->lock);
      if (ret < 0)
        {
          return ret;
        }

      /* Assume allocation failure */

      nbytes = -ENOMEM;

      /* Initialize a CBW (re-using the allocated transfer buffer) */

      cbw = usbhost_cbwalloc(priv);
      if (cbw)
        {
          /* Loop in the event that EAGAIN is returned (mean that the
           * transaction was NAKed and we should try again.
           */

          do
            {
              /* Assume some device failure */

              nbytes = -ENODEV;

              /* Construct and send the CBW */

              usbhost_readcbw(startsector, priv->blocksize, nsectors, cbw);
              nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                                     (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
              if (nbytes >= 0)
                {
                  /* Receive the user data */

                  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                         buffer, priv->blocksize * nsectors);
                  if (nbytes >= 0)
                    {
                      /* Receive the CSW */

                      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                             priv->tbuffer,
                                             USBMSC_CSW_SIZEOF);
                      if (nbytes >= 0)
                        {
                          FAR struct usbmsc_csw_s *csw;

                          /* Check the CSW status */

                          csw = (FAR struct usbmsc_csw_s *)priv->tbuffer;
                          if (csw->status != 0)
                            {
                              uerr("ERROR: CSW status error: %d\n",
                                   csw->status);
                              nbytes = -ENODEV;
                            }
                        }
                    }
                }
            }
          while (nbytes == -EAGAIN);
        }

      nxmutex_unlock(&priv->lock);
    }

  /* On success, return the number of blocks read */

  return nbytes < 0 ? (int)nbytes : nsectors;

#endif
}

static ssize_t usbhost_write(FAR struct inode *inode,
                             FAR const unsigned char *buffer,
                             blkcnt_t startsector, unsigned int nsectors)
{
#ifdef CONFIG_USBHOST_MSC_READONLY
  (void)inode;
  (void)buffer;
  (void)startsector;
  (void)nsectors;
  return -EROFS;
#else

  FAR struct usbhost_state_s *priv;
  FAR struct usbhost_hubport_s *hport;
  ssize_t nbytes;
  int ret;

  uinfo("sector: %" PRIuOFF " nsectors: %u\n", startsector, nsectors);

  DEBUGASSERT(inode->i_private);
  priv = inode->i_private;

  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;

  /* Check if the mass storage device is still connected */

  if (priv->disconnected)
    {
      /* No... the block driver is no longer bound to the class.  That means
       * that the USB storage device is no longer connected.  Refuse any
       * attempt to write to the device.
       */

      nbytes = -ENODEV;
    }
  else
    {
      FAR struct usbmsc_cbw_s *cbw;

      ret = nxmutex_lock(&priv->lock);
      if (ret < 0)
        {
          return ret;
        }

      /* Assume allocation failure */

      nbytes = -ENOMEM;

      /* Initialize a CBW (re-using the allocated transfer buffer) */

      cbw = usbhost_cbwalloc(priv);
      if (cbw)
        {
          /* Assume some device failure */

          nbytes = -ENODEV;

          /* Construct and send the CBW */

          usbhost_writecbw(startsector, priv->blocksize, nsectors, cbw);
          nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                                 (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
          if (nbytes >= 0)
            {
              /* Send the user data */

              nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                                     (FAR uint8_t *)buffer,
                                     priv->blocksize * nsectors);
              if (nbytes >= 0)
                {
                  /* Receive the CSW */

                  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                         priv->tbuffer, USBMSC_CSW_SIZEOF);
                  if (nbytes >= 0)
                    {
                      FAR struct usbmsc_csw_s *csw;

                      /* Check the CSW status */

                      csw = (FAR struct usbmsc_csw_s *)priv->tbuffer;
                      if (csw->status != 0)
                        {
                          uerr("ERROR: CSW status error: %d\n", csw->status);
                          nbytes = -ENODEV;
                        }
                    }
                }
            }
        }

      nxmutex_unlock(&priv->lock);
    }

  /* On success, return the number of blocks written */

  return nbytes < 0 ? (int)nbytes : nsectors;

#endif
}

static int usbhost_geometry(FAR struct inode *inode,
                            FAR struct geometry *geometry)
{
#ifdef CONFIG_USBHOST_MSC_READONLY
  FAR struct usbhost_state_s *priv = inode->i_private;
  int ret;
  if (geometry == NULL)
    {
      return -EINVAL;
    }

  ret = nxmutex_lock(&priv->lock);
  if (ret < 0)
    {
      return ret;
    }

  memset(geometry, 0, sizeof(*geometry));
  if (priv->disconnected || priv->bot_failed)
    {
      ret = -ENODEV;
    }
  else
    {
      geometry->geo_available = true;
      geometry->geo_writeenabled = false;
      geometry->geo_nsectors = priv->nblocks;
      geometry->geo_sectorsize = priv->blocksize;
      ret = OK;
    }

  nxmutex_unlock(&priv->lock);
  return ret;
#else

  FAR struct usbhost_state_s *priv;
  int ret = -EINVAL;

  uinfo("Entry\n");
  DEBUGASSERT(inode->i_private);

  /* Check if the mass storage device is still connected */

  priv = inode->i_private;
  if (priv->disconnected)
    {
      /* No... the block driver is no longer bound to the class.  That means
       * that the USB storage device is no longer connected.  Refuse to
       * return any geometry info.
       */

      ret = -ENODEV;
    }
  else if (geometry)
    {
      /* Return the geometry of the USB mass storage device */

      ret = nxmutex_lock(&priv->lock);
      if (ret >= 0)
        {
          memset(geometry, 0, sizeof(*geometry));

          geometry->geo_available     = true;
          geometry->geo_mediachanged  = false;
          geometry->geo_writeenabled  = true;
          geometry->geo_nsectors      = priv->nblocks;
          geometry->geo_sectorsize    = priv->blocksize;
          nxmutex_unlock(&priv->lock);

          uinfo("nsectors: %" PRIdOFF " sectorsize: %" PRIi16 "\n",
                geometry->geo_nsectors, geometry->geo_sectorsize);
        }
    }

  return ret;

#endif
}
#include "mock-tests.inc"
