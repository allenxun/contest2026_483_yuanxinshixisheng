from pathlib import Path
import datetime, shutil, difflib
r=Path('/home/swl/openvela'); w=r/'work/rk3576-usbhost'
p=r/'apps/examples/k7host/k7host_main.c';old=p.read_text()
shutil.copy2(p,w/('k7host-pre-warmup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.c'))
a='''  ret = k7_xhci_isoc_batch(drvr, g_video_ep, g_packet, best, g_batch_results);
  usleep(5000); printf("UVC ISO continuous batch ret=%d slots=2048\\n", ret);
  if (ret < 0) goto stop_camera;
  for (unsigned int packet_index = 0; packet_index < 2048; packet_index++)'''
b='''  /* This camera initially returns zero-length packets while starting its
   * sensor. Keep polling for up to four completed batches. Discard the
   * first partial frame of every batch, including gaps between batches. */
  for (unsigned int batch = 0; batch < 4 && !g_frame_len; batch++)
    {
      lastfid = -1; assembling = false; invalid = false; used = 0;
      ret = k7_xhci_isoc_batch(drvr, g_video_ep, g_packet, best, g_batch_results);
      usleep(5000); printf("UVC ISO batch=%u ret=%d slots=2048\\n", batch, ret);
      if (ret < 0) goto stop_camera;
  for (unsigned int packet_index = 0; packet_index < 2048; packet_index++)'''
assert a in old;new=old.replace(a,b)
new=new.replace('stop_camera:\n', '    }\nstop_camera:\n')
p.write_text(new)
(w/'uvc-warmup-v13.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/apps/examples/k7host/k7host_main.c',tofile='b/apps/examples/k7host/k7host_main.c')))
print('Allow up to four completed ISO batches for camera startup')
