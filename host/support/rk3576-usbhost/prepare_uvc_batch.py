from pathlib import Path
import datetime, tarfile, difflib
r=Path('/home/swl/openvela'); w=r/'work/rk3576-usbhost'
names=['apps/examples/k7host/k7host_main.c','nuttx/drivers/usbhost/usbhost_xhci_rk3576.c']
with tarfile.open(w/('pre-uvc-batch-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.tgz'),'w:gz') as z:
    for name in names:z.add(r/name,arcname=name)
patch=[]
for name in names:
    p=r/name; old=p.read_text(); new=old
    if name.endswith('usbhost_xhci_rk3576.c'):
        new=new.replace('  uint8_t            slot;         /* Slot where this EP resides */', '''  uint8_t            slot;         /* Slot where this EP resides */
  int32_t           *batch_result; /* Retained by bounded K7 diagnostic */
  unsigned int       batch_count;
  unsigned int       batch_done;
  size_t             batch_packet;
  bool               batch_active;''')
        new=new.replace('ring->ring = kmm_memalign(XHCI_BUF_ALIGN,',
                        'ring->ring = kmm_memalign(len > 256 ? 65536 : XHCI_BUF_ALIGN,')
        # Only periodic data rings are enlarged; EP0 and hub interrupts stay small.
        i=new.index('static int xhci_epalloc(',new.index('static int xhci_epalloc(')+1)
        j=new.index('static int xhci_epfree(',i)
        part=new[i:j].replace('xhci_ring_init(&epinfo->td, XHCI_TD_MAX)',
                             'xhci_ring_init(&epinfo->td, epdesc->xfrtype == USB_EP_ATTR_XFER_ISOC ? 2049 : XHCI_TD_MAX)')
        new=new[:i]+part+new[j:]
        a='''  /* Get EP associated with this transfer */

  epinfo = priv->devs[slot - 1].epinfo[ep - 1];
  DEBUGASSERT(epinfo != NULL);'''
        b='''  /* Ring empty events do not complete a TD (xHCI 4.17.4). In
   * particular, they must not consume a newly installed callback. */
  if (ret == XHCI_TRB_CC_RUR || ret == XHCI_TRB_CC_ROV)
    {
      return;
    }

  if (slot == 0 || slot > priv->no_slots || ep == 0 ||
      ep > XHCI_MAX_ENDPOINTS)
    {
      return;
    }
  epinfo = priv->devs[slot - 1].epinfo[ep - 1];
  if (epinfo == NULL) return;

  if (epinfo->batch_active)
    {
      uintptr_t base = k7_xhci_va_to_pa(epinfo->td.ring);
      uintptr_t address = evt->d0;
      unsigned int index;
      if (address < base || (address - base) % sizeof(struct xhci_trb_s)) return;
      index = (address - base) / sizeof(struct xhci_trb_s);
      if (index >= epinfo->batch_count ||
          epinfo->batch_result[index] != -EINPROGRESS) return;
      epinfo->batch_result[index] =
        (ret == XHCI_TRB_CC_SUCCESS || ret == XHCI_TRB_CC_SHORT_PKT) &&
        tl <= epinfo->batch_packet ? epinfo->batch_packet - tl : -EIO;
      if (++epinfo->batch_done == epinfo->batch_count)
        {
          epinfo->batch_active = false;
          epinfo->iocwait = false;
          epinfo->result = OK;
          nxsem_post(&epinfo->iocsem);
        }
      return;
    }'''
        assert a in new;new=new.replace(a,b)
        code=r'''
/* Bounded, one-shot bring-up API: queue 2048 HS microframes ahead of time.
 * Each buffer occupies its own 4 KiB slot, so no TRB crosses 64 KiB.
 * The caller retains buffers, result array and endpoint until board reset.
 * This diagnostic deliberately does not claim continuous streaming support. */
int k7_xhci_isoc_batch(struct usbhost_driver_s *drvr, usbhost_ep_t ep,
                      uint8_t *buffer, size_t packet, int32_t *results)
{
  struct usbhost_xhci_s *priv = XHCI_PRIV_FROM_DRVR(drvr);
  struct xhci_epinfo_s *info = (struct xhci_epinfo_s *)ep;
  struct xhci_trb_s *trbs;
  const unsigned int count = 2048;
  const size_t total = 2048 * 4096;
  int ret;
  if (!info || info->xfrtype != USB_EP_ATTR_XFER_ISOC || !info->dirin ||
      info->td.i != 0 || info->td.len != count + 1 || !buffer || !results ||
      (uintptr_t)buffer % 4096 || packet == 0 || packet > 3072)
    return -EINVAL;
  ret = nxmutex_lock(&info->exclsem);
  if (ret < 0) return ret;
  ret = nxmutex_lock(&priv->lock);
  if (ret < 0) { nxmutex_unlock(&info->exclsem); return ret; }
  if (info->iocwait || info->batch_active)
    { ret = -EBUSY; goto unlock; }
  trbs = kmm_zalloc(count * sizeof(*trbs));
  if (!trbs) { ret = -ENOMEM; goto unlock; }
  if (xhci_dma_prepare(priv, info, buffer, total, true) != buffer)
    { kmm_free(trbs); ret = -EINVAL; goto unlock; }
  for (unsigned int i = 0; i < count; i++)
    {
      results[i] = -EINPROGRESS;
      trbs[i].d0 = k7_xhci_va_to_pa(buffer + i * 4096);
      trbs[i].d1 = XHCI_TRB_D1_TXLEN_SET(packet);
      trbs[i].d2 = XHCI_TRB_D2_IOC | XHCI_TRB_D2_ISP | XHCI_TRB_D2_SIA |
                   XHCI_TRB_D2_TYPE_SET(XHCI_TRB_TYPE_ISOCH);
    }
  info->batch_result = results;
  info->batch_packet = packet;
  info->batch_count = count;
  info->batch_done = 0;
  info->batch_active = true;
  info->iocwait = true;
  info->result = -EBUSY;
  xhci_add_trb(priv, &info->td, trbs, count);
  kmm_free(trbs);
  xhci_ep_doorbell(priv, info);
  nxmutex_unlock(&priv->lock);
  ret = nxsem_tickwait_uninterruptible(&info->iocsem, SEC2TICK(2));
  if (ret >= 0)
    {
      /* Invalidate data only after every packet has completed. */
      xhci_dma_finish(info);
      ret = info->result;
    }
  /* Timeout retains the DMA mapping. Never free or reuse it here. */
  nxmutex_unlock(&info->exclsem);
  return ret;
unlock:
  nxmutex_unlock(&priv->lock);
  nxmutex_unlock(&info->exclsem);
  return ret;
}
'''
        # Insert after transfer completion so every static helper is defined.
        mark='/****************************************************************************\n * Name: xhci_envet_complete'
        assert mark in new;new=new.replace(mark,code+'\n'+mark)
    else:
        new=new.replace('static sem_t g_packet_sem = SEM_INITIALIZER(0);\nstatic ssize_t g_packet_result;',
                        'static int32_t g_batch_results[2048];\nextern int k7_xhci_isoc_batch(struct usbhost_driver_s *, usbhost_ep_t, uint8_t *, size_t, int32_t *);')
        i=new.index('static void packet_done(');j=new.index('static void camera_snapshot(',i)
        new=new[:i]+new[j:]
        new=new.replace('  size_t used = 0, alloclen = 0;', '  size_t used = 0;')
        new=new.replace('  clock_t begin;','')
        new=new.replace('''  ret = DRVR_ALLOC(drvr, &g_packet, &alloclen);
  if (ret < 0 || alloclen < best) { ret = -ENOMEM; goto done; }''', '''  g_packet = kmm_memalign(4096, 2048 * 4096);
  if (!g_packet) { ret = -ENOMEM; goto done; }''')
        i=new.index('  begin = clock_systime_ticks();');j=new.index('      if (packets < 8)',i)
        new=new[:i]+'''  ret = k7_xhci_isoc_batch(drvr, g_video_ep, g_packet, best, g_batch_results);
  usleep(5000); printf("UVC ISO continuous batch ret=%d slots=2048\\n", ret);
  if (ret < 0) goto stop_camera;
  for (unsigned int packet_index = 0; packet_index < 2048; packet_index++)
    {
      ssize_t n = g_batch_results[packet_index];
      uint8_t *packet_data = g_packet + packet_index * 4096;
      unsigned int h, flags, fid;
      if (n < 0) { bad++; invalid = true; continue; }
'''+new[j:]
        i=new.index('  for (unsigned int packet_index');j=new.index('  /* No memory or endpoint free here',i)
        part=new[i:j].replace('g_packet[','packet_data[').replace('g_packet,','packet_data,').replace('g_packet + h','packet_data + h')
        new=new[:i]+part+new[j:]
        new=new.replace('  /* No memory or endpoint free here', 'stop_camera:\n  /* No memory or endpoint free here')
    assert new!=old
    p.write_text(new)
    patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(w/'uvc-batch-v12.patch').write_text(''.join(patch))
print('Added one-shot 2048-packet ISO batch and transferless ring-event handling')
