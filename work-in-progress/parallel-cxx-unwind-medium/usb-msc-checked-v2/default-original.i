struct usbhost_state_s
{
  struct usbhost_class_s usbclass;
  char sdchar;
  volatile bool disconnected;
  uint8_t ifno;
  int16_t crefs;
  uint16_t blocksize;
  uint32_t nblocks;
  spinlock_t spinlock;
  mutex_t lock;
  struct work_s work;
  FAR uint8_t *tbuffer;
  size_t tbuflen;
  usbhost_ep_t bulkin;
  usbhost_ep_t bulkout;
};
struct usbhost_freestate_s
{
  FAR struct usbhost_freestate_s *flink;
};
static inline FAR struct usbhost_state_s *usbhost_allocclass(void);
static inline void usbhost_freeclass(FAR struct usbhost_state_s *usbclass);
static int usbhost_allocdevno(FAR struct usbhost_state_s *priv);
static void usbhost_freedevno(FAR struct usbhost_state_s *priv);
static inline void usbhost_mkdevname(FAR struct usbhost_state_s *priv,
                                     FAR char *devname);
static inline void usbhost_requestsensecbw(FAR struct usbmsc_cbw_s *cbw);
static inline void usbhost_testunitreadycbw(FAR struct usbmsc_cbw_s *cbw);
static inline void usbhost_readcapacitycbw(FAR struct usbmsc_cbw_s *cbw);
static inline void usbhost_inquirycbw (FAR struct usbmsc_cbw_s *cbw);
static inline void usbhost_readcbw (blkcnt_t startsector, uint16_t blocksize,
                                    unsigned int nsectors,
                                    FAR struct usbmsc_cbw_s *cbw);
static inline void usbhost_writecbw(blkcnt_t startsector, uint16_t blocksize,
                                    unsigned int nsectors,
                                    FAR struct usbmsc_cbw_s *cbw);
static inline int usbhost_maxlunreq(FAR struct usbhost_state_s *priv);
static inline int usbhost_testunitready(FAR struct usbhost_state_s *priv);
static inline int usbhost_requestsense(FAR struct usbhost_state_s *priv);
static inline int usbhost_readcapacity(FAR struct usbhost_state_s *priv);
static inline int usbhost_inquiry(FAR struct usbhost_state_s *priv);
static void usbhost_destroy(FAR void *arg);
static inline int usbhost_cfgdesc(FAR struct usbhost_state_s *priv,
                                  FAR const uint8_t *configdesc,
                                  int desclen);
static inline int usbhost_initvolume(FAR struct usbhost_state_s *priv);
static inline uint16_t usbhost_getle16(const uint8_t *val);
static inline uint16_t usbhost_getbe16(const uint8_t *val);
static inline void usbhost_putle16(uint8_t *dest, uint16_t val);
static inline void usbhost_putbe16(uint8_t *dest, uint16_t val);
static inline uint32_t usbhost_getbe32(const uint8_t *val);
static void usbhost_putle32(uint8_t *dest, uint32_t val);
static void usbhost_putbe32(uint8_t *dest, uint32_t val);
static inline int usbhost_talloc(FAR struct usbhost_state_s *priv);
static inline int usbhost_tfree(FAR struct usbhost_state_s *priv);
static FAR struct usbmsc_cbw_s *
       usbhost_cbwalloc(FAR struct usbhost_state_s *priv);
static struct usbhost_class_s *
  usbhost_create(FAR struct usbhost_hubport_s *hport,
                 FAR const struct usbhost_id_s *id);
static int usbhost_connect(FAR struct usbhost_class_s *usbclass,
                           FAR const uint8_t *configdesc, int desclen);
static int usbhost_disconnected(FAR struct usbhost_class_s *usbclass);
static int usbhost_open(FAR struct inode *inode);
static int usbhost_close(FAR struct inode *inode);
static ssize_t usbhost_read(FAR struct inode *inode,
                            FAR unsigned char *buffer, blkcnt_t startsector,
                            unsigned int nsectors);
static ssize_t usbhost_write(FAR struct inode *inode,
                             FAR const unsigned char *buffer,
                             blkcnt_t startsector, unsigned int nsectors);
static int usbhost_geometry(FAR struct inode *inode,
                            FAR struct geometry *geometry);
static int usbhost_ioctl(FAR struct inode *inode, int cmd,
                         unsigned long arg);
static const struct usbhost_id_s g_id =
{
  USB_CLASS_MASS_STORAGE,
  USBMSC_SUBCLASS_SCSI,
  USBMSC_PROTO_BULKONLY,
  0,
  0
};
static struct usbhost_registry_s g_storage =
{
  NULL,
  usbhost_create,
  1,
  &g_id
};
static const struct block_operations g_bops =
{
  usbhost_open,
  usbhost_close,
  usbhost_read,
  usbhost_write,
  usbhost_geometry,
  usbhost_ioctl
};
static struct usbhost_state_s g_prealloc[4];
static FAR struct usbhost_freestate_s *g_freelist;
static uint32_t g_devinuse;
static spinlock_t g_lock = SP_UNLOCKED;
static inline FAR struct usbhost_state_s *usbhost_allocclass(void)
{
  FAR struct usbhost_freestate_s *entry;
  irqstate_t flags;
  flags = spin_lock_irqsave(&g_lock);
  entry = g_freelist;
  if (entry)
    {
      g_freelist = entry->flink;
    }
  spin_unlock_irqrestore(&g_lock, flags);
  uinfo("Allocated: %p\n", entry);
  return (FAR struct usbhost_state_s *)entry;
}
static inline void usbhost_freeclass(FAR struct usbhost_state_s *usbclass)
{
  FAR struct usbhost_freestate_s *entry =
    (FAR struct usbhost_freestate_s *)usbclass;
  irqstate_t flags;
  DEBUGASSERT(entry != NULL);
  uinfo("Freeing: %p\n", entry);
  flags = spin_lock_irqsave(&g_lock);
  entry->flink = g_freelist;
  g_freelist = entry;
  spin_unlock_irqrestore(&g_lock, flags);
}
static int usbhost_allocdevno(FAR struct usbhost_state_s *priv)
{
  irqstate_t flags;
  int devno;
  flags = spin_lock_irqsave(&g_lock);
  for (devno = 0; devno < 26; devno++)
    {
      uint32_t bitno = 1 << devno;
      if ((g_devinuse & bitno) == 0)
        {
          g_devinuse |= bitno;
          priv->sdchar = 'a' + devno;
          spin_unlock_irqrestore(&g_lock, flags);
          return OK;
        }
    }
  spin_unlock_irqrestore(&g_lock, flags);
  return -EMFILE;
}
static void usbhost_freedevno(FAR struct usbhost_state_s *priv)
{
  int devno = priv->sdchar - 'a';
  if (devno >= 0 && devno < 26)
    {
      irqstate_t flags = spin_lock_irqsave(&g_lock);
      g_devinuse &= ~(1 << devno);
      spin_unlock_irqrestore(&g_lock, flags);
    }
}
static inline void usbhost_mkdevname(FAR struct usbhost_state_s *priv,
                                     FAR char *devname)
{
  snprintf(devname, 10, "/dev/sd%c", priv->sdchar);
}
static inline void usbhost_requestsensecbw(FAR struct usbmsc_cbw_s *cbw)
{
  FAR struct scsicmd_requestsense_s *reqsense;
  usbhost_putle32(cbw->datlen, SCSIRESP_FIXEDSENSEDATA_SIZEOF);
  cbw->flags = USBMSC_CBWFLAG_IN;
  cbw->cdblen = SCSICMD_REQUESTSENSE_SIZEOF;
  reqsense = (FAR struct scsicmd_requestsense_s *)cbw->cdb;
  reqsense->opcode = SCSI_CMD_REQUESTSENSE;
  reqsense->alloclen = SCSIRESP_FIXEDSENSEDATA_SIZEOF;
  ;;
}
static inline void usbhost_testunitreadycbw(FAR struct usbmsc_cbw_s *cbw)
{
  cbw->cdblen = SCSICMD_TESTUNITREADY_SIZEOF;
  cbw->cdb[0] = SCSI_CMD_TESTUNITREADY;
  ;;
}
static inline void usbhost_readcapacitycbw(FAR struct usbmsc_cbw_s *cbw)
{
  FAR struct scsicmd_readcapacity10_s *rcap10;
  usbhost_putle32(cbw->datlen, SCSIRESP_READCAPACITY10_SIZEOF);
  cbw->flags = USBMSC_CBWFLAG_IN;
  cbw->cdblen = SCSICMD_READCAPACITY10_SIZEOF;
  rcap10 = (FAR struct scsicmd_readcapacity10_s *)cbw->cdb;
  rcap10->opcode = SCSI_CMD_READCAPACITY10;
  ;;
}
static inline void usbhost_inquirycbw (FAR struct usbmsc_cbw_s *cbw)
{
  FAR struct scscicmd_inquiry_s *inq;
  usbhost_putle32(cbw->datlen, SCSIRESP_INQUIRY_SIZEOF);
  cbw->flags = USBMSC_CBWFLAG_IN;
  cbw->cdblen = SCSICMD_INQUIRY_SIZEOF;
  inq = (FAR struct scscicmd_inquiry_s *)cbw->cdb;
  inq->opcode = SCSI_CMD_INQUIRY;
  usbhost_putbe16(inq->alloclen, SCSIRESP_INQUIRY_SIZEOF);
  ;;
}
static inline void
usbhost_readcbw (blkcnt_t startsector, uint16_t blocksize,
                 unsigned int nsectors, FAR struct usbmsc_cbw_s *cbw)
{
  FAR struct scsicmd_read10_s *rd10;
  usbhost_putle32(cbw->datlen, blocksize * nsectors);
  cbw->flags = USBMSC_CBWFLAG_IN;
  cbw->cdblen = SCSICMD_READ10_SIZEOF;
  rd10 = (FAR struct scsicmd_read10_s *)cbw->cdb;
  rd10->opcode = SCSI_CMD_READ10;
  usbhost_putbe32(rd10->lba, startsector);
  usbhost_putbe16(rd10->xfrlen, nsectors);
  ;;
}
static inline void
usbhost_writecbw(blkcnt_t startsector, uint16_t blocksize,
                 unsigned int nsectors, FAR struct usbmsc_cbw_s *cbw)
{
  FAR struct scsicmd_write10_s *wr10;
  usbhost_putle32(cbw->datlen, blocksize * nsectors);
  cbw->cdblen = SCSICMD_WRITE10_SIZEOF;
  wr10 = (FAR struct scsicmd_write10_s *)cbw->cdb;
  wr10->opcode = SCSI_CMD_WRITE10;
  usbhost_putbe32(wr10->lba, startsector);
  usbhost_putbe16(wr10->xfrlen, nsectors);
  ;;
}
static inline int usbhost_maxlunreq(FAR struct usbhost_state_s *priv)
{
  FAR struct usb_ctrlreq_s *req = (FAR struct usb_ctrlreq_s *)priv->tbuffer;
  FAR struct usbhost_hubport_s *hport;
  DEBUGASSERT(priv && priv->tbuffer);
  int ret;
  uinfo("Request maximum logical unit number\n");
  memset(req, 0, sizeof(struct usb_ctrlreq_s));
  req->type = USB_DIR_IN | USB_REQ_TYPE_CLASS |
                 USB_REQ_RECIPIENT_INTERFACE;
  req->req = USBMSC_REQ_GETMAXLUN;
  usbhost_putle16(req->len, 1);
  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;
  ret = DRVR_CTRLIN(hport->drvr, hport->ep0, req, priv->tbuffer);
  if (ret < 0)
    {
      *(priv->tbuffer) = 0;
    }
  return OK;
}
static inline int usbhost_testunitready(FAR struct usbhost_state_s *priv)
{
  FAR struct usbhost_hubport_s *hport;
  FAR struct usbmsc_cbw_s *cbw;
  ssize_t nbytes;
  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;
  cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      uerr("ERROR: Failed to create CBW\n");
      return -ENOMEM;
    }
  usbhost_testunitreadycbw(cbw);
  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                        (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
  if (nbytes >= 0)
    {
      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                             priv->tbuffer, USBMSC_CSW_SIZEOF);
      if (nbytes >= 0)
        {
          ;;
        }
    }
  return nbytes < 0 ? (int)nbytes : OK;
}
static inline int usbhost_requestsense(FAR struct usbhost_state_s *priv)
{
  FAR struct usbhost_hubport_s *hport;
  FAR struct usbmsc_cbw_s *cbw;
  ssize_t nbytes;
  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;
  cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      uerr("ERROR: Failed to create CBW\n");
      return -ENOMEM;
    }
  usbhost_requestsensecbw(cbw);
  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                        (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
  if (nbytes >= 0)
    {
      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                             priv->tbuffer, SCSIRESP_FIXEDSENSEDATA_SIZEOF);
      if (nbytes >= 0)
        {
          nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                 priv->tbuffer, USBMSC_CSW_SIZEOF);
          if (nbytes >= 0)
            {
              ;;
            }
        }
    }
  return nbytes < 0 ? (int)nbytes : OK;
}
static inline int usbhost_readcapacity(FAR struct usbhost_state_s *priv)
{
  FAR struct usbhost_hubport_s *hport;
  FAR struct usbmsc_cbw_s *cbw;
  FAR struct scsiresp_readcapacity10_s *resp;
  ssize_t nbytes;
  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;
  cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      uerr("ERROR: Failed to create CBW\n");
      return -ENOMEM;
    }
  usbhost_readcapacitycbw(cbw);
  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                        (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
  if (nbytes >= 0)
    {
      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                             priv->tbuffer, SCSIRESP_READCAPACITY10_SIZEOF);
      if (nbytes >= 0)
        {
          resp = (FAR struct scsiresp_readcapacity10_s *)
                            priv->tbuffer;
          priv->nblocks = usbhost_getbe32(resp->lba) + 1;
          priv->blocksize = usbhost_getbe32(resp->blklen);
          nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                 priv->tbuffer, USBMSC_CSW_SIZEOF);
          if (nbytes >= 0)
            {
              ;;
            }
        }
    }
  return nbytes < 0 ? (int)nbytes : OK;
}
static inline int usbhost_inquiry(FAR struct usbhost_state_s *priv)
{
  FAR struct usbhost_hubport_s *hport;
  FAR struct usbmsc_cbw_s *cbw;
  ssize_t nbytes;
  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;
  cbw = usbhost_cbwalloc(priv);
  if (!cbw)
    {
      uerr("ERROR: Failed to create CBW\n");
      return -ENOMEM;
    }
  usbhost_inquirycbw(cbw);
  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                         (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
  if (nbytes >= 0)
    {
      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                             priv->tbuffer, SCSIRESP_INQUIRY_SIZEOF);
      if (nbytes >= 0)
        {
          nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                 priv->tbuffer, USBMSC_CSW_SIZEOF);
          if (nbytes >= 0)
            {
              ;;
            }
        }
    }
  return nbytes < 0 ? (int)nbytes : OK;
}
static void usbhost_destroy(FAR void *arg)
{
  FAR struct usbhost_state_s *priv = (FAR struct usbhost_state_s *)arg;
  FAR struct usbhost_hubport_s *hport;
  char devname[10];
  DEBUGASSERT(priv != NULL && priv->usbclass.hport != NULL);
  hport = priv->usbclass.hport;
  uinfo("crefs: %d\n", priv->crefs);
  usbhost_mkdevname(priv, devname);
  unregister_blockdriver(devname);
  usbhost_freedevno(priv);
  if (priv->bulkout)
    {
      DRVR_EPFREE(hport->drvr, priv->bulkout);
    }
  if (priv->bulkin)
    {
      DRVR_EPFREE(hport->drvr, priv->bulkin);
    }
  usbhost_tfree(priv);
  nxmutex_destroy(&priv->lock);
  DRVR_DISCONNECT(hport->drvr, hport);
  usbhost_devaddr_destroy(hport, hport->funcaddr);
  hport->funcaddr = 0;
  usbhost_freeclass(priv);
}
static inline int usbhost_cfgdesc(FAR struct usbhost_state_s *priv,
                                  FAR const uint8_t *configdesc, int desclen)
{
  FAR struct usbhost_hubport_s *hport;
  FAR struct usb_cfgdesc_s *cfgdesc;
  FAR struct usb_desc_s *desc;
  FAR struct usbhost_epdesc_s bindesc;
  FAR struct usbhost_epdesc_s boutdesc;
  int remaining;
  uint8_t found = 0;
  int ret;
  DEBUGASSERT(priv != NULL && priv->usbclass.hport &&
              configdesc != NULL && desclen >= sizeof(struct usb_cfgdesc_s));
  hport = priv->usbclass.hport;
  memset(&bindesc, 0, sizeof(struct usbhost_epdesc_s));
  memset(&boutdesc, 0, sizeof(struct usbhost_epdesc_s));
  cfgdesc = (FAR struct usb_cfgdesc_s *)configdesc;
  if (cfgdesc->type != USB_DESC_TYPE_CONFIG)
    {
      return -EINVAL;
    }
  remaining = (int)usbhost_getle16(cfgdesc->totallen);
  configdesc += cfgdesc->len;
  remaining -= cfgdesc->len;
  while (remaining >= sizeof(struct usb_desc_s))
    {
      desc = (FAR struct usb_desc_s *)configdesc;
      switch (desc->type)
        {
        case USB_DESC_TYPE_INTERFACE:
          {
            FAR struct usb_ifdesc_s *ifdesc =
              (FAR struct usb_ifdesc_s *)configdesc;
            uinfo("Interface descriptor\n");
            DEBUGASSERT(remaining >= USB_SIZEOF_IFDESC);
            priv->ifno = ifdesc->ifno;
            found = 0x01;
          }
          break;
        case USB_DESC_TYPE_ENDPOINT:
          {
            FAR struct usb_epdesc_s *epdesc =
              (FAR struct usb_epdesc_s *)configdesc;
            uinfo("Endpoint descriptor\n");
            DEBUGASSERT(remaining >= USB_SIZEOF_EPDESC);
            if ((epdesc->attr & USB_EP_ATTR_XFERTYPE_MASK) ==
                USB_EP_ATTR_XFER_BULK)
              {
                if (USB_ISEPOUT(epdesc->addr))
                  {
                    if ((found & 0x04) != 0)
                      {
                        return -EINVAL;
                      }
                    found |= 0x04;
                    boutdesc.hport = hport;
                    boutdesc.addr = epdesc->addr &
                                            USB_EP_ADDR_NUMBER_MASK;
                    boutdesc.in = false;
                    boutdesc.xfrtype = USB_EP_ATTR_XFER_BULK;
                    boutdesc.interval = epdesc->interval;
                    boutdesc.mxpacketsize =
                      usbhost_getle16(epdesc->mxpacketsize);
                    uinfo("Bulk OUT EP addr:%d mxpacketsize:%d\n",
                          boutdesc.addr, boutdesc.mxpacketsize);
                  }
                else
                  {
                    if ((found & 0x02) != 0)
                      {
                        return -EINVAL;
                      }
                    found |= 0x02;
                    bindesc.hport = hport;
                    bindesc.addr = epdesc->addr &
                                           USB_EP_ADDR_NUMBER_MASK;
                    bindesc.in = 1;
                    bindesc.xfrtype = USB_EP_ATTR_XFER_BULK;
                    bindesc.interval = epdesc->interval;
                    bindesc.mxpacketsize =
                      usbhost_getle16(epdesc->mxpacketsize);
                    uinfo("Bulk IN EP addr:%d mxpacketsize:%d\n",
                          bindesc.addr, bindesc.mxpacketsize);
                  }
              }
          }
          break;
        default:
          break;
        }
      if (found == 0x07)
        {
          break;
        }
      configdesc += desc->len;
      remaining -= desc->len;
    }
  if (found != 0x07)
    {
      uerr("ERROR: Found IF:%s BIN:%s BOUT:%s\n",
           (found & 0x01) != 0 ? "YES" : "NO",
           (found & 0x02) != 0 ? "YES" : "NO",
           (found & 0x04) != 0 ? "YES" : "NO");
      return -EINVAL;
    }
  ret = DRVR_EPALLOC(hport->drvr, &boutdesc, &priv->bulkout);
  if (ret < 0)
    {
      uerr("ERROR: Failed to allocate Bulk OUT endpoint\n");
      return ret;
    }
  ret = DRVR_EPALLOC(hport->drvr, &bindesc, &priv->bulkin);
  if (ret < 0)
    {
      uerr("ERROR: Failed to allocate Bulk IN endpoint\n");
      DRVR_EPFREE(hport->drvr, priv->bulkout);
      return ret;
    }
  uinfo("Endpoints allocated\n");
  return OK;
}
static inline int usbhost_initvolume(FAR struct usbhost_state_s *priv)
{
  FAR struct usbmsc_csw_s *csw;
  unsigned int retries;
  int ret = OK;
  DEBUGASSERT(priv != NULL);
  ret = usbhost_talloc(priv);
  if (ret < 0)
    {
      uerr("ERROR: Failed to allocate transfer buffer\n");
      return ret;
    }
  priv->crefs++;
  DEBUGASSERT(priv->crefs == 2);
  uinfo("Get max LUN\n");
  ret = usbhost_maxlunreq(priv);
  for (retries = 0; retries < 100; retries++)
    {
      uinfo("Test unit ready, retries=%d\n", retries);
      nxsig_usleep((50*1000));
      ret = usbhost_testunitready(priv);
      if (ret >= 0)
        {
          csw = (FAR struct usbmsc_csw_s *)priv->tbuffer;
          if (csw->status == 0)
            {
              break;
            }
          uinfo("Request sense\n");
          ret = usbhost_requestsense(priv);
        }
      if (ret < 0 && ret != -EPERM)
        {
          uerr("ERROR: DRVR_TRANSFER returned: %d\n", ret);
          break;
        }
    }
  if (retries >= 100)
    {
      uerr("ERROR: Timeout!\n");
      ret = -ETIMEDOUT;
    }
  if (ret >= 0)
    {
      uinfo("Read capacity\n");
      ret = usbhost_readcapacity(priv);
      if (ret >= 0)
        {
          csw = (FAR struct usbmsc_csw_s *)priv->tbuffer;
          if (csw->status != 0)
            {
              uerr("ERROR: CSW status error: %d\n", csw->status);
              ret = -ENODEV;
            }
        }
    }
  if (ret >= 0)
    {
      uinfo("Inquiry\n");
      ret = usbhost_inquiry(priv);
      if (ret >= 0)
        {
          csw = (FAR struct usbmsc_csw_s *)priv->tbuffer;
          if (csw->status != 0)
            {
              uerr("ERROR: CSW status error: %d\n", csw->status);
              ret = -ENODEV;
            }
        }
    }
  if (ret >= 0)
    {
      char devname[10];
      uinfo("Register block driver\n");
      usbhost_mkdevname(priv, devname);
      ret = register_blockdriver(devname, &g_bops, 0, priv);
    }
  nxmutex_lock(&priv->lock);
  DEBUGASSERT(priv->crefs >= 2);
  priv->crefs--;
  if (ret >= 0 && priv->crefs <= 1 && priv->disconnected)
    {
      ret = -ENODEV;
    }
  nxmutex_unlock(&priv->lock);
  return ret;
}
static inline uint16_t usbhost_getle16(const uint8_t *val)
{
  return (uint16_t)val[1] << 8 | (uint16_t)val[0];
}
static inline uint16_t usbhost_getbe16(const uint8_t *val)
{
  return (uint16_t)val[0] << 8 | (uint16_t)val[1];
}
static void usbhost_putle16(uint8_t *dest, uint16_t val)
{
  dest[0] = val & 0xff;
  dest[1] = val >> 8;
}
static void usbhost_putbe16(uint8_t *dest, uint16_t val)
{
  dest[0] = val >> 8;
  dest[1] = val & 0xff;
}
static inline uint32_t usbhost_getbe32(const uint8_t *val)
{
  return (uint32_t)usbhost_getbe16(val) << 16 |
         (uint32_t)usbhost_getbe16(&val[2]);
}
static void usbhost_putle32(uint8_t *dest, uint32_t val)
{
  usbhost_putle16(dest, (uint16_t)(val & 0xffff));
  usbhost_putle16(dest + 2, (uint16_t)(val >> 16));
}
static void usbhost_putbe32(uint8_t *dest, uint32_t val)
{
  usbhost_putbe16(dest, (uint16_t)(val >> 16));
  usbhost_putbe16(dest + 2, (uint16_t)(val & 0xffff));
}
static inline int usbhost_talloc(FAR struct usbhost_state_s *priv)
{
  FAR struct usbhost_hubport_s *hport;
  DEBUGASSERT(priv != NULL && priv->usbclass.hport != NULL &&
              priv->tbuffer == NULL);
  hport = priv->usbclass.hport;
  return DRVR_ALLOC(hport->drvr, &priv->tbuffer, &priv->tbuflen);
}
static inline int usbhost_tfree(FAR struct usbhost_state_s *priv)
{
  FAR struct usbhost_hubport_s *hport;
  int result = OK;
  DEBUGASSERT(priv != NULL && priv->usbclass.hport != NULL);
  if (priv->tbuffer)
    {
      hport = priv->usbclass.hport;
      result = DRVR_FREE(hport->drvr, priv->tbuffer);
      priv->tbuffer = NULL;
      priv->tbuflen = 0;
    }
  return result;
}
static FAR struct usbmsc_cbw_s *
  usbhost_cbwalloc(FAR struct usbhost_state_s *priv)
{
  FAR struct usbmsc_cbw_s *cbw = NULL;
  DEBUGASSERT(priv->tbuffer && priv->tbuflen >= sizeof(struct usbmsc_cbw_s));
  cbw = (FAR struct usbmsc_cbw_s *)priv->tbuffer;
  memset(cbw, 0, sizeof(struct usbmsc_cbw_s));
  usbhost_putle32(cbw->signature, USBMSC_CBW_SIGNATURE);
  return cbw;
}
static FAR struct usbhost_class_s *
  usbhost_create(FAR struct usbhost_hubport_s *hport,
                 FAR const struct usbhost_id_s *id)
{
  FAR struct usbhost_state_s *priv;
  priv = usbhost_allocclass();
  if (priv)
    {
      memset(priv, 0, sizeof(struct usbhost_state_s));
      if (usbhost_allocdevno(priv) == OK)
        {
          priv->usbclass.hport = hport;
          priv->usbclass.connect = usbhost_connect;
          priv->usbclass.disconnected = usbhost_disconnected;
          priv->crefs = 1;
          nxmutex_init(&priv->lock);
          spin_lock_init(&priv->spinlock);
          return &priv->usbclass;
        }
    }
  if (priv)
    {
      usbhost_freeclass(priv);
    }
  return NULL;
}
static int usbhost_connect(FAR struct usbhost_class_s *usbclass,
                           FAR const uint8_t *configdesc, int desclen)
{
  FAR struct usbhost_state_s *priv = (FAR struct usbhost_state_s *)usbclass;
  int ret;
  DEBUGASSERT(priv != NULL &&
              configdesc != NULL &&
              desclen >= sizeof(struct usb_cfgdesc_s));
  ret = usbhost_cfgdesc(priv, configdesc, desclen);
  if (ret < 0)
    {
      uerr("ERROR: usbhost_cfgdesc() failed: %d\n", ret);
    }
  else
    {
      ret = usbhost_initvolume(priv);
      if (ret < 0)
        {
          uerr("ERROR: usbhost_initvolume() failed: %d\n", ret);
        }
    }
  return ret;
}
static int usbhost_disconnected(struct usbhost_class_s *usbclass)
{
  FAR struct usbhost_state_s *priv = (FAR struct usbhost_state_s *)usbclass;
  irqstate_t flags;
  DEBUGASSERT(priv != NULL);
  flags = spin_lock_irqsave(&priv->spinlock);
  priv->disconnected = true;
  if (priv->crefs == 1)
    {
      spin_unlock_irqrestore(&priv->spinlock, flags);
      if (up_interrupt_context())
        {
          uinfo("Queuing destruction: worker %p->%p\n",
                priv->work.worker, usbhost_destroy);
          DEBUGASSERT(priv->work.worker == NULL);
          work_queue(HPWORK, &priv->work, usbhost_destroy, priv, 0);
        }
      else
        {
          usbhost_destroy(priv);
        }
      return OK;
    }
  spin_unlock_irqrestore(&priv->spinlock, flags);
  return OK;
}
static int usbhost_open(FAR struct inode *inode)
{
  FAR struct usbhost_state_s *priv;
  irqstate_t flags;
  int ret;
  uinfo("Entry\n");
  DEBUGASSERT(inode->i_private);
  priv = inode->i_private;
  DEBUGASSERT(priv->crefs > 0 && priv->crefs < INT16_MAX);
  ret = nxmutex_lock(&priv->lock);
  if (ret < 0)
    {
      return ret;
    }
  flags = spin_lock_irqsave(&priv->spinlock);
  if (priv->disconnected)
    {
      ret = -ENODEV;
    }
  else
    {
      priv->crefs++;
      ret = OK;
    }
  spin_unlock_irqrestore(&priv->spinlock, flags);
  nxmutex_unlock(&priv->lock);
  return ret;
}
static int usbhost_close(FAR struct inode *inode)
{
  FAR struct usbhost_state_s *priv;
  irqstate_t flags;
  uinfo("Entry\n");
  DEBUGASSERT(inode->i_private);
  priv = inode->i_private;
  DEBUGASSERT(priv->crefs > 1);
  nxmutex_lock(&priv->lock);
  flags = spin_lock_irqsave(&priv->spinlock);
  priv->crefs--;
  if (priv->crefs <= 1 && priv->disconnected)
    {
      DEBUGASSERT(priv->crefs == 1);
      spin_unlock_irqrestore(&priv->spinlock, flags);
      nxmutex_unlock(&priv->lock);
      usbhost_destroy(priv);
      return OK;
    }
  spin_unlock_irqrestore(&priv->spinlock, flags);
  nxmutex_unlock(&priv->lock);
  return OK;
}
static ssize_t usbhost_read(FAR struct inode *inode, unsigned char *buffer,
                            blkcnt_t startsector, unsigned int nsectors)
{
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
  if (priv->disconnected)
    {
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
      nbytes = -ENOMEM;
      cbw = usbhost_cbwalloc(priv);
      if (cbw)
        {
          do
            {
              nbytes = -ENODEV;
              usbhost_readcbw(startsector, priv->blocksize, nsectors, cbw);
              nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                                     (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
              if (nbytes >= 0)
                {
                  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                         buffer, priv->blocksize * nsectors);
                  if (nbytes >= 0)
                    {
                      nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                             priv->tbuffer,
                                             USBMSC_CSW_SIZEOF);
                      if (nbytes >= 0)
                        {
                          FAR struct usbmsc_csw_s *csw;
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
  return nbytes < 0 ? (int)nbytes : nsectors;
}
static ssize_t usbhost_write(FAR struct inode *inode,
                             FAR const unsigned char *buffer,
                             blkcnt_t startsector, unsigned int nsectors)
{
  FAR struct usbhost_state_s *priv;
  FAR struct usbhost_hubport_s *hport;
  ssize_t nbytes;
  int ret;
  uinfo("sector: %" PRIuOFF " nsectors: %u\n", startsector, nsectors);
  DEBUGASSERT(inode->i_private);
  priv = inode->i_private;
  DEBUGASSERT(priv->usbclass.hport);
  hport = priv->usbclass.hport;
  if (priv->disconnected)
    {
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
      nbytes = -ENOMEM;
      cbw = usbhost_cbwalloc(priv);
      if (cbw)
        {
          nbytes = -ENODEV;
          usbhost_writecbw(startsector, priv->blocksize, nsectors, cbw);
          nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                                 (FAR uint8_t *)cbw, USBMSC_CBW_SIZEOF);
          if (nbytes >= 0)
            {
              nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkout,
                                     (FAR uint8_t *)buffer,
                                     priv->blocksize * nsectors);
              if (nbytes >= 0)
                {
                  nbytes = DRVR_TRANSFER(hport->drvr, priv->bulkin,
                                         priv->tbuffer, USBMSC_CSW_SIZEOF);
                  if (nbytes >= 0)
                    {
                      FAR struct usbmsc_csw_s *csw;
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
  return nbytes < 0 ? (int)nbytes : nsectors;
}
static int usbhost_geometry(FAR struct inode *inode,
                            FAR struct geometry *geometry)
{
  FAR struct usbhost_state_s *priv;
  int ret = -EINVAL;
  uinfo("Entry\n");
  DEBUGASSERT(inode->i_private);
  priv = inode->i_private;
  if (priv->disconnected)
    {
      ret = -ENODEV;
    }
  else if (geometry)
    {
      ret = nxmutex_lock(&priv->lock);
      if (ret >= 0)
        {
          memset(geometry, 0, sizeof(*geometry));
          geometry->geo_available = true;
          geometry->geo_mediachanged = false;
          geometry->geo_writeenabled = true;
          geometry->geo_nsectors = priv->nblocks;
          geometry->geo_sectorsize = priv->blocksize;
          nxmutex_unlock(&priv->lock);
          uinfo("nsectors: %" PRIdOFF " sectorsize: %" PRIi16 "\n",
                geometry->geo_nsectors, geometry->geo_sectorsize);
        }
    }
  return ret;
}
static int usbhost_ioctl(FAR struct inode *inode, int cmd, unsigned long arg)
{
  FAR struct usbhost_state_s *priv;
  int ret;
  uinfo("Entry\n");
  DEBUGASSERT(inode->i_private);
  priv = inode->i_private;
  if (priv->disconnected)
    {
      ret = -ENODEV;
    }
  else
    {
      ret = nxmutex_lock(&priv->lock);
      if (ret >= 0)
        {
          switch (cmd)
            {
              default:
                ret = -ENOTTY;
                break;
            }
          nxmutex_unlock(&priv->lock);
        }
    }
  return ret;
}
int usbhost_msc_initialize(void)
{
  FAR struct usbhost_freestate_s *entry;
  int i;
  g_freelist = NULL;
  for (i = 0; i < 4; i++)
    {
      entry = (FAR struct usbhost_freestate_s *)&g_prealloc[i];
      entry->flink = g_freelist;
      g_freelist = entry;
    }
  return usbhost_registerclass(&g_storage);
}
