/* Included after fw_wifi_target_scan. One serialized operation; existing RX
 * worker owns the FIFO. This probe stops before WPA association/key exchange.
 */
static enum skw_mgmt_kind g_wifi_wait_kind=SKW_MGMT_AUTH;
static uint16_t g_wifi_assoc_aid;
static void fw_wifi_mgmt_event(uint8_t instance,const uint8_t *p,size_t n)
{
  struct skw_mgmt_result result;
  int ret;
  if (nxmutex_lock(&g_wifi_state)) return;
  if (!g_wifi_auth_waiting || instance!=g_wifi_join_instance)
    { nxmutex_unlock(&g_wifi_state); return; }
  ret=skw_mgmt_decode(p,n,g_wifi_mac,g_wifi_join_bss.scan.bssid,
    g_wifi_join_bss.scan.channel,g_wifi_join_bss.scan.band,&result);
  if (ret)
    printf("RADIO Wi-Fi ignored malformed management ret=%d bytes=%zu\n",ret,n);
  else if (result.kind==g_wifi_wait_kind)
    {
      g_wifi_auth_status=result.status;g_wifi_assoc_aid=result.aid;
      g_wifi_auth_received=true;g_wifi_auth_waiting=false;
      printf("RADIO Wi-Fi management response status=%u kind=%u\n",
        result.status,result.kind);
      nxsem_post(&g_wifi_authsem);
    }
  nxmutex_unlock(&g_wifi_state);
}

static int fw_wifi_join_probe(bool associate)
{
  static uint8_t params[25+SKW_BSS_IE_MAX];
  uint8_t open[10]={1,0},auth[14],disconnect[8];
  struct skw_join_reply reply;
  size_t bytes;
  bool opened=false,joined=false,auth_ok=false,assoc_ok=false;
  int ret,unjoin=0,close_ret=0;
  ret=fw_wifi_target_scan();
  if (ret) return ret;
  if ((ret=nxmutex_lock(&g_wifi_state))) return ret;
  memcpy(&g_wifi_join_bss,&g_wifi_target,sizeof(g_wifi_join_bss));
  nxmutex_unlock(&g_wifi_state);
  const struct skw_bss *b=&g_wifi_join_bss;
  if (!b->rsn || b->unknown_suite || b->group_cipher!=4 ||
      !(b->pairwise&(1u<<4)) || !(b->akm&(1u<<2))) return -ENOTSUP;
  ret=skw_join_encode(b->scan.channel,b->scan.band,b->beacon_interval,
    b->capability,b->scan.bssid,b->ies,b->ie_len,params,sizeof(params),&bytes);
  if (ret) return ret;
  memcpy(open+4,g_wifi_mac,6);
  ret=fw_wifi_command(3,open,sizeof(open));
  if (ret) return ret;
  opened=true;
  ret=fw_wifi_command(9,params,bytes);
  if (ret) goto done;
  joined=true;
  ret=skw_join_reply_decode(g_wifi_response,g_wifi_response_len,&reply);
  if (ret) goto done;
  printf("RADIO Wi-Fi JOIN peer=%u lmac=%u instance=%u multicast=%u\n",
    reply.peer,reply.lmac,reply.instance,reply.multicast);
  /* This candidate registers only station instance 0. */
  if (reply.instance!=0) { ret=-EPROTO; goto done; }
  if ((ret=nxmutex_lock(&g_wifi_state))) goto done;
  while (nxsem_trywait(&g_wifi_authsem)==0) {}
  g_wifi_join_instance=reply.instance;
  g_wifi_wait_kind=SKW_MGMT_AUTH;g_wifi_auth_received=false;g_wifi_auth_status=0xffff;g_wifi_auth_waiting=true;
  nxmutex_unlock(&g_wifi_state);
  ret=skw_auth_open_encode(auth,sizeof(auth));
  if (!ret) ret=fw_wifi_command(10,auth,sizeof(auth));
  if (!ret) ret=nxsem_tickwait_uninterruptible(&g_wifi_authsem,MSEC2TICK(3000));
  if (nxmutex_lock(&g_wifi_state)==0)
    {
      g_wifi_auth_waiting=false;
      if (!ret && (!g_wifi_auth_received || g_wifi_auth_status)) ret=-EACCES;
      auth_ok=!ret && g_wifi_auth_received && !g_wifi_auth_status;
      nxmutex_unlock(&g_wifi_state);
    }
  else if (!ret) ret=-EIO;
  if (!ret && associate)
    {
      /* Explicit narrow WPA2-PSK/CCMP association proposal, no PMF support.
       * Full supplicant will later generate its own negotiated RSN IE.
       * This probe does not accept or send EAPOL-Key messages.
       */
      static const uint8_t rsn[]={0x30,20,1,0,0,15,172,4,1,0,0,15,172,4,
                                  1,0,0,15,172,2,0,0};
      bool compatible=false;
      for (size_t pos=0;pos+2<=b->ie_len;pos+=2+b->ies[pos+1])
        if (b->ies[pos]==48 && b->ies[pos+1]==20 &&
            pos+22<=b->ie_len && !(b->ies[pos+20]&0x40)) compatible=true;
      if (!compatible) { ret=-ENOTSUP; goto done; }
      ret=skw_assoc_encode(b->scan.bssid,rsn,sizeof(rsn),params,sizeof(params),&bytes);
      if (ret) goto done;
      if ((ret=nxmutex_lock(&g_wifi_state))) goto done;
      while (nxsem_trywait(&g_wifi_authsem)==0) {}
      g_wifi_wait_kind=SKW_MGMT_ASSOC;g_wifi_assoc_aid=0;
      g_wifi_auth_received=false;g_wifi_auth_status=0xffff;g_wifi_auth_waiting=true;
      nxmutex_unlock(&g_wifi_state);
      ret=fw_wifi_command(11,params,bytes);
      if (!ret) ret=nxsem_tickwait_uninterruptible(&g_wifi_authsem,MSEC2TICK(3000));
      if (nxmutex_lock(&g_wifi_state)==0)
        {
          g_wifi_auth_waiting=false;
          if (!ret && (!g_wifi_auth_received || g_wifi_auth_status ||
              !g_wifi_assoc_aid || g_wifi_assoc_aid>2007)) ret=-EACCES;
          assoc_ok=!ret;
          printf("RADIO Wi-Fi association response_ok=%u status=%u AID=%u ret=%d\n",
            assoc_ok,g_wifi_auth_status,g_wifi_assoc_aid,ret);
          nxmutex_unlock(&g_wifi_state);
        }
      else if (!ret) ret=-EIO;
      if (!ret) usleep(1500000); /* Observe bounded initial data arrival only. */
    }
done:
  if (joined)
    {
      unjoin=skw_disconnect_encode(3,disconnect,sizeof(disconnect));
      if (!unjoin) unjoin=fw_wifi_command(17,disconnect,sizeof(disconnect));
    }
  if (opened) close_ret=fw_wifi_command(4,NULL,0);
  printf("RADIO Wi-Fi JOIN/AUTH probe auth_response_ok=%u assoc_response_ok=%u ret=%d unjoin=%d close=%d; WPA_completed=0 IP_acquired=0\n",
    auth_ok,assoc_ok,ret,unjoin,close_ret);
  return ret ? ret : (unjoin ? unjoin : close_ret);
}
