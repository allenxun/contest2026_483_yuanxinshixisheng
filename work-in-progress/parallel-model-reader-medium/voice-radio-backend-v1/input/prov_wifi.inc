/* Provisioning worker bridge; never run association/DHCP on Bluetooth LPWORK.
 * Disconnecting BLE suppresses delivery to a new session; the accepted network
 * operation continues, so its real state can be queried after reconnect. */
#ifdef CONFIG_EXAMPLES_K7RADIO_IP
#define PROV_CONNECT_CAP "true"
static bool prov_wifi_snapshot(char ip[16])
{
 nxmutex_lock(&g_wifi_ip_state);
 bool online=__atomic_load_n(&g_wifi_network_active,__ATOMIC_ACQUIRE) &&
   !g_wifi_ip_result && g_wifi_ip[0];
 memcpy(ip,g_wifi_ip,16);if(!online)ip[0]=0;
 nxmutex_unlock(&g_wifi_ip_state);return online;
}
static int prov_wifi_connect(const struct prov_request *req)
{
 int ret=nxmutex_trylock(&g_wifi_operation);
 if(ret)return -EBUSY;
 if(__atomic_load_n(&g_wifi_network_active,__ATOMIC_ACQUIRE))
   {
    __atomic_store_n(&g_wifi_network_stop,true,__ATOMIC_RELEASE);
    uint64_t deadline=now_us()+5000000;
    while(__atomic_load_n(&g_wifi_network_active,__ATOMIC_ACQUIRE) && now_us()<deadline)usleep(5000);
    if(__atomic_load_n(&g_wifi_network_active,__ATOMIC_ACQUIRE))
      {nxmutex_unlock(&g_wifi_operation);return -EBUSY;}
   }
 nxmutex_lock(&g_wifi_state);
 memcpy(g_wifi_target_ssid,req->ssid,req->ssid_len);g_wifi_target_ssid_len=req->ssid_len;
 nxmutex_unlock(&g_wifi_state);
 ret=fw_wifi_join_run(true,req->password);
 nxmutex_lock(&g_wifi_state);
 memset(g_wifi_target_ssid,0,sizeof(g_wifi_target_ssid));
 memcpy(g_wifi_target_ssid,"Lansee",6);g_wifi_target_ssid_len=6;
 nxmutex_unlock(&g_wifi_state);
 nxmutex_unlock(&g_wifi_operation);return ret;
}
#else
#define PROV_CONNECT_CAP "false"
static bool prov_wifi_snapshot(char ip[16]){ip[0]=0;return false;}
static int prov_wifi_connect(const struct prov_request *req){(void)req;return -ENOSYS;}
#endif
static const char *prov_wifi_error(int ret)
{
 switch(ret)
   {
    case -ENOENT:return "network_not_found";
    case -ENOTSUP:return "unsupported_security";
    case -EACCES:return "authentication_failed";
    case -ETIMEDOUT:return "connection_timeout";
    case -EBUSY:return "busy";
    case -ENOSYS:return "not_ready";
    default:return "connection_failed";
   }
}
