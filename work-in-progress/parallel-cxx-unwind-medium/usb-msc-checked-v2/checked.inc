#ifdef CONFIG_USBHOST_MSC_READONLY
/* Caller serializes with priv->lock, or is the unpublished connect path.
 * Never restart a partially issued BOT transaction. A new class instance
 * after re-enumeration is required after a transport/protocol failure. */
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
#endif
