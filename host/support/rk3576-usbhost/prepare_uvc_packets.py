from pathlib import Path
import datetime, tarfile, difflib
r=Path('/home/swl/openvela'); w=r/'work/rk3576-usbhost'
names=['apps/examples/k7host/k7host_main.c','nuttx/drivers/usbhost/usbhost_xhci_rk3576.c']
with tarfile.open(w/('pre-uvc-packets-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.tgz'),'w:gz') as z:
    for name in names:z.add(r/name,arcname=name)
patch=[]
for name in names:
    p=r/name; old=p.read_text(); new=old
    if name.endswith('usbhost_xhci_rk3576.c'):
        a='''  ctx->ctx2 = htole64(ctx2);

  /* Flush context */'''
        b='''  ctx->ctx2 = htole64(ctx2);
  /* Periodic bandwidth is required for isochronous IN endpoints.
   * HS wMaxPacketSize transaction count is encoded as Max Burst Size. */
  if (type == XHCI_EPTYPE_ISO_IN || type == XHCI_EPTYPE_ISO_OUT ||
      type == XHCI_EPTYPE_INTR_IN || type == XHCI_EPTYPE_INTR_OUT)
    {
      uint32_t payload = (uint32_t)maxpkt * (maxburst + 1) * (mult + 1);
      ctx->ctx3 = htole32((payload << XHCI_EP_CTX3_MESITLO_SHIFT) |
                          payload);
    }
  else
    {
      ctx->ctx3 = htole32(type == XHCI_EPTYPE_CTRL ? 8 : 0);
    }

  /* Flush context */'''
        assert a in new; new=new.replace(a,b)
        a='''                    eptype, epdesc->mxpacketsize, 0,
                    k7_xhci_va_to_pa(epinfo->td.ring),'''
        b='''                    eptype, epdesc->mxpacketsize & 0x7ff,
                    hport->speed == USB_SPEED_HIGH &&
                    (epdesc->xfrtype == USB_EP_ATTR_XFER_ISOC ||
                     epdesc->xfrtype == USB_EP_ATTR_XFER_INT) ?
                    (epdesc->mxpacketsize >> 11) & 3 : 0,
                    k7_xhci_va_to_pa(epinfo->td.ring),'''
        assert a in new; new=new.replace(a,b)
    else:
        new=new.replace('#include <stdio.h>', '#include <stdio.h>\n#include <unistd.h>\n#include <nuttx/clock.h>\n#include <nuttx/semaphore.h>')
        new=new.replace('static uint8_t g_vsif;', 'static uint8_t g_vsif;\nstatic struct usbhost_hubport_s *g_camera_hport;')
        new=new.replace('  g_camera_port = *c->hport;', '  g_camera_hport = c->hport;\n  g_camera_port = *c->hport;')
        new=new.replace('  printf("camera connected=%u descriptor_bytes=%d\\n", g_connected, g_desclen);',
                        '  printf("camera connected=%u committed=%u descriptor_bytes=%d\\n", g_connected, g_committed, g_desclen);')
        # Pace diagnostic bursts only, not video data.
        new=new.replace('  printf("UVC ', '  usleep(5000);\n  printf("UVC ')
        code=r'''
/* One bounded capture attempt per boot while the experimental HCD endpoint
 * teardown is being validated. Retain endpoint and DMA memory until reset;
 * a timeout must never free memory that hardware may still write. */
static bool g_capture_attempted;
static sem_t g_packet_sem = SEM_INITIALIZER(0);
static ssize_t g_packet_result;
static uint8_t *g_packet;
static uint8_t *g_frame;
static size_t g_frame_len;
static usbhost_ep_t g_video_ep;

static void packet_done(void *arg, ssize_t result)
{
  g_packet_result = result;
  nxsem_post(&g_packet_sem);
}

static void camera_snapshot(void)
{
  struct usbhost_driver_s *drvr = g_camera_port.drvr;
  struct usbhost_epdesc_s ep = {0};
  int offset = 0, alt = -1, interface = -1, chosen_alt = -1;
  unsigned int capacity = 0, best = 0xffff, packets = 0, bytes = 0;
  unsigned int headers = 0, errors = 0, eof = 0, changes = 0;
  unsigned int bad = 0, jpeg_candidates = 0;
  uint32_t required = le32(g_probe + 22), limit = le32(g_probe + 18);
  uint8_t samples[8][12] = {{0}};
  unsigned int sample_len[8] = {0};
  size_t used = 0, alloclen = 0;
  bool assembling = false, invalid = false;
  int lastfid = -1, ret = -ENODEV;
  clock_t begin;
  nxmutex_lock(&g_lock);
  if (!camera_connected() || !g_committed) goto done;
  if (g_capture_attempted) { ret = -EALREADY; goto done; }
  if (g_camera_port.speed != USB_SPEED_HIGH || !required || required > 3072 ||
      !limit || limit > 4*1024*1024) { ret = -ENOTSUP; goto done; }
  while (offset < g_desclen)
    {
      const uint8_t *d = g_desc + offset;
      unsigned int n = d[0];
      if (n < 2 || n > g_desclen - offset) { ret = -EINVAL; goto done; }
      if (d[1] == 4 && n >= 9) { interface = d[2]; alt = d[3]; }
      else if (d[1] == 5 && n >= 7 && interface == g_vsif && alt > 0 &&
               (d[2] & 0x80) && (d[3] & 3) == 1)
        {
          unsigned int raw = le16(d + 4);
          capacity = (raw & 0x7ff) * (1 + ((raw >> 11) & 3));
          if (capacity >= required && capacity < best && d[6] == 1)
            { chosen_alt = alt; best = capacity;
              ep.addr = d[2] & 15; ep.mxpacketsize = raw;
              ep.interval = d[6]; }
        }
      offset += n;
    }
  if (chosen_alt < 1) { ret = -ENOSPC; goto done; }
  g_capture_attempted = true;
  ep.hport = g_camera_hport;
  ep.in = true; ep.xfrtype = USB_EP_ATTR_XFER_ISOC;
  ret = DRVR_ALLOC(drvr, &g_packet, &alloclen);
  if (ret < 0 || alloclen < best) { ret = -ENOMEM; goto done; }
  g_frame = kmm_malloc(limit);
  if (!g_frame) { ret = -ENOMEM; goto done; }
  printf("UVC ISO configure EP=%02x alt=%d capacity=%u raw=%04x\n",
         ep.addr | 0x80, chosen_alt, best, ep.mxpacketsize);
  ret = DRVR_EPALLOC(drvr, &ep, &g_video_ep);
  usleep(5000); printf("UVC ISO EPALLOC ret=%d\n", ret);
  if (ret < 0) goto done;
  ret = camera_query(0x01, 11, chosen_alt, g_vsif, NULL, 0);
  usleep(5000); printf("UVC ISO SET_INTERFACE ret=%d\n", ret);
  if (ret < 0) goto done;
  begin = clock_systime_ticks();
  while (packets < 2048 && clock_systime_ticks() - begin < SEC2TICK(8) &&
         camera_connected())
    {
      ssize_t n;
      unsigned int h, flags, fid;
      ret = DRVR_ASYNCH(drvr, g_video_ep, g_packet, best, packet_done, NULL);
      if (ret < 0) break;
      ret = nxsem_tickwait_uninterruptible(&g_packet_sem, MSEC2TICK(250));
      if (ret < 0) break; /* Retain the entire DMA lifetime on timeout. */
      n = g_packet_result;
      if (n < 0) { ret = n; break; }
      if (packets < 8)
        { sample_len[packets] = n;
          memcpy(samples[packets], g_packet, n < 12 ? n : 12); }
      packets++; bytes += n;
      if (n == 0) continue;
      if (n < 2 || n > best || g_packet[0] < 2 || g_packet[0] > n)
        { bad++; invalid = true; continue; }
      h = g_packet[0]; flags = g_packet[1]; fid = flags & 1;
      headers++;
      if (lastfid != (int)fid)
        {
          if (lastfid >= 0) { assembling = true; changes++; }
          lastfid = fid; used = 0; invalid = false;
        }
      if (flags & 0x40) { errors++; invalid = true; }
      if (assembling && !invalid)
        {
          if (used + n - h > limit) { bad++; invalid = true; }
          else { memcpy(g_frame + used, g_packet + h, n - h); used += n - h; }
        }
      if (flags & 2)
        {
          eof++;
          if (assembling && !invalid && used >= 4 &&
              g_frame[0] == 0xff && g_frame[1] == 0xd8 &&
              g_frame[used-2] == 0xff && g_frame[used-1] == 0xd9)
            { g_frame_len = used; jpeg_candidates++; break; }
          assembling = false;
        }
    }
  /* No memory or endpoint free here, even if stopping the camera fails. */
  if (camera_connected())
    {
      int stopret = camera_query(0x01, 11, 0, g_vsif, NULL, 0);
      usleep(5000); printf("UVC ISO alt0 stop ret=%d\n", stopret);
    }
done:
  usleep(5000);
  printf("UVC ISO result=%d packets=%u bytes=%u headers=%u errors=%u bad=%u\n",
         ret, packets, bytes, headers, errors, bad);
  usleep(5000);
  printf("UVC boundaries fid_changes=%u eof=%u JPEG_candidates=%u retained=%u\n",
         changes, eof, jpeg_candidates, (unsigned)g_frame_len);
  for (unsigned int i = 0; i < packets && i < 8; i++)
    {
      usleep(5000); printf("UVC packet[%u] bytes=%u head=", i, sample_len[i]);
      for (unsigned int j = 0; j < 12 && j < sample_len[i]; j++) printf("%02x", samples[i][j]);
      printf("\n");
    }
  nxmutex_unlock(&g_lock);
}
'''
        new=new.replace('int k7host_main(int argc, char *argv[])',code+'\nint k7host_main(int argc, char *argv[])')
        new=new.replace('  if (!strcmp(argv[1], "probe"))', '  if (!strcmp(argv[1], "snapshot")) { camera_snapshot(); return 0; }\n  if (!strcmp(argv[1], "probe"))')
        new=new.replace('start | camera | probe','start | camera | probe | snapshot')
    assert new!=old
    p.write_text(new)
    patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(w/'uvc-packets-v11.patch').write_text(''.join(patch))
print('Added bounded UVC ISO snapshot diagnostic and HS periodic endpoint bandwidth')
