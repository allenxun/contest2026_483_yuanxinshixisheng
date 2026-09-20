static int fw_wifi_scan(void)
{
#ifdef CONFIG_EXAMPLES_K7RADIO_IP
  if(__atomic_load_n(&g_wifi_network_active,__ATOMIC_ACQUIRE))return -EBUSY;
#endif
  const uint8_t *calib = (const void *)0x50190000;
  const uint8_t five[] = {36, 40, 44, 48, 149, 153, 157, 161, 165};
  uint8_t chunk[516] = {0}, open[10] = {1, 0}, scan[98] = {0};
  int ret, stop = 0, close;
  if (!g_wifi_info_valid) return -EAGAIN;
  if (!g_wifi_calibrated)
    {
      if (skw_crc16(0, calib, 2372) != 0xd20d) return -EBADMSG;
      for (size_t offset = 0, seq = 0; offset < 2372; seq++)
        {
          size_t bytes = 2372 - offset;
          if (bytes > 512) bytes = 512;
          memset(chunk, 0, sizeof(chunk));
          chunk[0] = seq; chunk[1] = offset + bytes == 2372;
          chunk[2] = bytes & 255; chunk[3] = bytes >> 8;
          memcpy(chunk + 4, calib + offset, bytes);
          ret = fw_wifi_command(50, chunk, sizeof(chunk));
          printf("RADIO Wi-Fi calibration seq=%zu bytes=%zu end=%u ret=%d\n",
                 seq, bytes, chunk[1], ret);
          if (ret) return ret;
          offset += bytes;
        }
      g_wifi_calibrated = true;
    }
  memcpy(open + 4, g_wifi_mac, 6);
  ret = fw_wifi_command(3, open, sizeof(open));
  if (ret) goto scan_close;
  /* Passive scan: no SSID probe requests and no association. */
  scan[8] = 22; scan[12] = 32;
  for (unsigned int i = 0; i < 22; i++)
    {
      scan[32 + i * 3] = i < 13 ? i + 1 : five[i - 13];
      scan[33 + i * 3] = i < 13 ? 0 : 1;
      scan[34 + i * 3] = 0x80;
    }
  if ((ret = nxmutex_lock(&g_wifi_state))) goto scan_close;
  while (nxsem_trywait(&g_wifi_scansem) == 0) {}
  g_wifi_scan_done = false; g_wifi_reports = 0; g_wifi_unique = 0;
  nxmutex_unlock(&g_wifi_state);
  ret = fw_wifi_command(5, scan, sizeof(scan));
  if (!ret)
    ret = g_bt_host_mode ? nxsem_tickwait_uninterruptible(&g_wifi_scansem, MSEC2TICK(8000)) : fw_receive(8000);
  int check=nxmutex_lock(&g_wifi_state);
  if(!check){if(!ret&&!g_wifi_scan_done)ret=-ETIMEDOUT;nxmutex_unlock(&g_wifi_state);}
  else if(!ret)ret=check;
  if (ret) stop = fw_wifi_command(6, NULL, 0);
scan_close:
  close = fw_wifi_command(4, NULL, 0);
  int locked = nxmutex_lock(&g_wifi_state);
  if (locked) return locked;
  printf("RADIO Wi-Fi passive scan reports=%u unique=%u done=%u ret=%d stop=%d close=%d; network_connected=0\n",
         g_wifi_reports, g_wifi_unique, g_wifi_scan_done, ret, stop, close);
  if (!ret && !g_wifi_scan_done) ret = -ETIMEDOUT;
  nxmutex_unlock(&g_wifi_state);
  return ret ? ret : (stop ? stop : close);
}
