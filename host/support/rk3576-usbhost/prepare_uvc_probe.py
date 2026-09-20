from pathlib import Path
import datetime, tarfile, difflib

root = Path('/home/swl/openvela')
work = root / 'work/rk3576-usbhost'
path = root / 'apps/examples/k7host/k7host_main.c'
old = path.read_text()
assert 'static void camera_probe' not in old
with tarfile.open(work / ('pre-uvc-probe-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.tgz'), 'w:gz') as z:
    for name in ['apps/examples/k7host/k7host_main.c', 'nuttx/arch/arm64/src/rk3576/rk3576_usbhost.c', 'nuttx/arch/arm64/src/rk3576/rk3576_boot.c']:
        z.add(root / name, arcname=name)
new = old.replace('/* Enumeration probe for the user\'s 32e6:9221 camera. No video streaming. */',
                  '/* Bounded bring-up diagnostics for the 32e6:9221 UVC camera. */')
new = new.replace('#include <nuttx/mutex.h>', '#include <nuttx/mutex.h>\n#include <nuttx/irq.h>')
new = new.replace('static int g_desclen;', '''static int g_desclen;
/* Retain this diagnostic instance until reset. Disconnect must never wait
 * for g_lock: a control transfer may need the HCD worker to finish. */
static bool g_created;
static struct usbhost_hubport_s g_camera_port;
static uint8_t g_probe[26];
static bool g_committed;
static uint8_t g_vsif;
static void put16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static void put32(uint8_t *p, uint32_t v)
{ p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }
static uint32_t le32(const uint8_t *p)
{ return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static bool camera_connected(void)
{
  irqstate_t flags = enter_critical_section();
  bool connected = g_connected;
  leave_critical_section(flags);
  return connected;
}''')
new = new.replace('  g_connected = true;', '  g_camera_port = *c->hport;\n  g_connected = true;')
start = new.index('  /* This class submits no transfers')
end = new.index('\n  return 0;', start)
new = new[:start] + '''  irqstate_t flags = enter_critical_section();
  g_connected = false;
  g_committed = false;
  leave_critical_section(flags);
  /* One diagnostic instance per boot. No premature free during control I/O. */''' + new[end:]
new = new.replace('  c = kmm_zalloc(sizeof(*c));', '  if (g_created) return NULL;\n  c = kmm_zalloc(sizeof(*c));')
new = new.replace('      c->hport = port;', '      g_created = true;\n      c->hport = port;')
code = r'''
/* UVC 1.0 VS controls have a 26-byte layout. Request and data allocations
 * are separate DMA-safe HCD buffers. Run a probe in the background during
 * bring-up so NSH remains available if the experimental HCD stalls. */
static int camera_query(uint8_t type, uint8_t request, uint16_t value,
                        uint16_t index, uint8_t *data, uint16_t len)
{
  struct usbhost_driver_s *drvr = g_camera_port.drvr;
  struct usb_ctrlreq_s *req;
  uint8_t *setup = NULL;
  uint8_t *buffer = NULL;
  size_t setup_len, buffer_len;
  int ret;
  if (!camera_connected()) return -ENODEV;
  ret = DRVR_ALLOC(drvr, &setup, &setup_len);
  if (ret < 0) return ret;
  ret = DRVR_ALLOC(drvr, &buffer, &buffer_len);
  if (ret < 0) goto done;
  if (setup_len < sizeof(*req) || buffer_len < len)
    { ret = -ENOMEM; goto done; }
  req = (struct usb_ctrlreq_s *)setup;
  req->type = type;
  req->req = request;
  put16(req->value, value);
  put16(req->index, index);
  put16(req->len, len);
  memset(buffer, 0, buffer_len);
  if (!(type & 0x80) && len) memcpy(buffer, data, len);
  ret = (type & 0x80) ? DRVR_CTRLIN(drvr, g_camera_port.ep0, req, buffer) :
                       DRVR_CTRLOUT(drvr, g_camera_port.ep0, req, buffer);
  if (ret >= 0 && (type & 0x80) && len) memcpy(data, buffer, len);
done:
  if (buffer) DRVR_FREE(drvr, buffer);
  DRVR_FREE(drvr, setup);
  return ret;
}

static void camera_probe(void)
{
  int offset = 0, cls = -1, sub = -1, interface = -1;
  int format = -1, wanted_format = -1, wanted_frame = -1;
  unsigned int version = 0;
  uint32_t interval = 0;
  uint8_t probe[26] = {0};
  int ret = -ENODEV;
  nxmutex_lock(&g_lock);
  g_committed = false;
  if (!camera_connected()) goto done;
  while (offset < g_desclen)
    {
      const uint8_t *d = g_desc + offset;
      unsigned int n = d[0];
      if (n < 2 || n > g_desclen - offset) { ret = -EINVAL; goto done; }
      if (d[1] == 4 && n >= 9)
        { interface = d[2]; cls = d[5]; sub = d[6]; }
      else if (d[1] == 0x24 && n >= 5 && cls == 14 && sub == 1 && d[2] == 1)
        version = le16(d + 3);
      else if (d[1] == 0x24 && n >= 4 && cls == 14 && sub == 2)
        {
          if (d[2] == 6) format = d[3];
          else if (d[2] == 4) format = -1;
          else if (d[2] == 7 && n >= 26 && format > 0 &&
                   le16(d + 5) == 640 && le16(d + 7) == 480)
            { wanted_format = format; wanted_frame = d[3];
              interval = le32(d + 21); g_vsif = interface; }
        }
      offset += n;
    }
  if (version != 0x0100 || wanted_format < 1 || wanted_frame < 1 || !interval)
    { ret = -ENOTSUP; goto done; }
  printf("UVC request MJPEG 640x480 format=%d frame=%d interval=%" PRIu32 " IF=%u\n",
         wanted_format, wanted_frame, interval, g_vsif);
  ret = camera_query(0x01, 11, 0, g_vsif, NULL, 0);
  printf("UVC SET_INTERFACE alt0 ret=%d\n", ret);
  if (ret < 0) goto done;
  ret = camera_query(0xa1, 0x81, 0x0100, g_vsif, probe, sizeof(probe));
  printf("UVC GET_CUR PROBE ret=%d\n", ret);
  if (ret < 0) goto done;
  put16(probe, 1);
  probe[2] = wanted_format; probe[3] = wanted_frame;
  put32(probe + 4, interval);
  put32(probe + 18, 0); put32(probe + 22, 0);
  ret = camera_query(0x21, 1, 0x0100, g_vsif, probe, sizeof(probe));
  printf("UVC SET_CUR PROBE ret=%d\n", ret);
  if (ret < 0) goto done;
  memset(probe, 0, sizeof(probe));
  ret = camera_query(0xa1, 0x81, 0x0100, g_vsif, probe, sizeof(probe));
  printf("UVC negotiated ret=%d format=%u frame=%u interval=%" PRIu32
         " max_frame=%" PRIu32 " payload=%" PRIu32 "\n", ret,
         probe[2], probe[3], le32(probe+4), le32(probe+18), le32(probe+22));
  if (ret < 0) goto done;
  if (probe[2] != wanted_format || probe[3] != wanted_frame ||
      le32(probe+4) != interval || !le32(probe+18) ||
      le32(probe+18) > 4*1024*1024 || !le32(probe+22) || le32(probe+22) > 3072)
    { ret = -ERANGE; goto done; }
  ret = camera_query(0x21, 1, 0x0200, g_vsif, probe, sizeof(probe));
  printf("UVC SET_CUR COMMIT ret=%d\n", ret);
  if (ret >= 0 && camera_connected())
    { memcpy(g_probe, probe, sizeof(probe)); g_committed = true; }
done:
  printf("UVC probe result=%d committed=%u (no streaming yet)\n", ret, g_committed);
  nxmutex_unlock(&g_lock);
}
'''
new = new.replace('int k7host_main(int argc, char *argv[])', code + '\nint k7host_main(int argc, char *argv[])')
new = new.replace('  if (!strcmp(argv[1], "camera"))', '  if (!strcmp(argv[1], "probe")) { camera_probe(); return 0; }\n  if (!strcmp(argv[1], "camera"))')
new = new.replace('Usage: k7host start | camera', 'Usage: k7host start | camera | probe')
new = new.replace('Enumeration only: no UVC PROBE/COMMIT or frame capture yet.', 'Use k7host probe for UVC negotiation; no frame capture yet.')
path.write_text(new)
(work / 'uvc-probe-v9.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='a/apps/examples/k7host/k7host_main.c', tofile='b/apps/examples/k7host/k7host_main.c')))
print('UVC probe command installed with source backup')
