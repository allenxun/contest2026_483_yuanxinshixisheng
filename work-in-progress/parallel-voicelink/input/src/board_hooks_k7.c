/****************************************************************************
 * src/board_hooks_k7.c
 *
 * Board hooks for KICKPI K7 + openvela.
 * ES8388 speech is provided by the speech_engine.h implementation.
 * VS6621SR80 Wi-Fi via NuttX wapi (wireless API).
 *
 * NEVER log the Wi-Fi password.
 ****************************************************************************/

#include "voicelink/board_hooks.h"
#include "voicelink/speech_engine.h"

#include <errno.h>
#include <nuttx/wireless/wireless.h>
#include <string.h>
#include <syslog.h>
#include <unistd.h>
#include <wireless/wapi.h>

/****************************************************************************
 * Wi-Fi interface name (K7 + VS6621SR80 STA mode)
 ****************************************************************************/

#ifdef CONFIG_APP_VOICELINK_WIFI_IFNAME
#define VOICELINK_WIFI_IFNAME CONFIG_APP_VOICELINK_WIFI_IFNAME
#else
#define VOICELINK_WIFI_IFNAME "wlan0"
#endif

/****************************************************************************
 * voicelink_board_tts_speak
 ****************************************************************************/

int voicelink_board_tts_speak(const char *utf8_text)
{
  if (utf8_text == NULL)
    {
      return -EINVAL;
    }

  return voicelink_speech_speak(utf8_text);
}

/****************************************************************************
 * voicelink_board_tts_stop
 ****************************************************************************/

int voicelink_board_tts_stop(void)
{
  return voicelink_speech_stop();
}

/****************************************************************************
 * voicelink_board_wifi_scan
 *
 * Scan for nearby access points using the NuttX wapi library.
 * Fills up to *capacity* entries. Returns 0 on success.
 ****************************************************************************/

int voicelink_board_wifi_scan(struct voicelink_ap *aps, size_t capacity,
                              size_t *count)
{
  struct wapi_list_s list;
  FAR struct wapi_scan_info_s *info;
  int sock;
  int ret;
  int tries;

  if (aps == NULL || count == NULL || capacity == 0)
    {
      return -EINVAL;
    }

  *count = 0;

  sock = wapi_make_socket();
  if (sock < 0)
    {
      syslog(LOG_ERR, "voicelink: wapi_make_socket failed: %d\n", sock);
      return sock;
    }

  /* Ensure the interface is up */

  ret = wapi_set_ifup(sock, VOICELINK_WIFI_IFNAME);
  if (ret < 0)
    {
      syslog(LOG_ERR, "voicelink: ifup %s failed: %d\n",
             VOICELINK_WIFI_IFNAME, ret);
      close(sock);
      return ret;
    }

  /* Trigger an active scan */

  ret = wapi_escan_init(sock, VOICELINK_WIFI_IFNAME,
                        IW_SCAN_TYPE_ACTIVE, NULL);
  if (ret < 0)
    {
      syslog(LOG_ERR, "voicelink: escan_init failed: %d\n", ret);
      close(sock);
      return ret;
    }

  /* Wait for scan to complete (up to 5 seconds) */

  for (tries = 0; tries < 25; tries++)
    {
      ret = wapi_scan_stat(sock, VOICELINK_WIFI_IFNAME);
      if (ret == 0)
        {
          break;  /* Scan complete */
        }

      if (ret < 0)
        {
          syslog(LOG_ERR, "voicelink: scan_stat failed: %d\n", ret);
          close(sock);
          return ret;
        }

      usleep(200 * 1000); /* 200 ms */
    }

  if (tries >= 25)
    {
      syslog(LOG_ERR, "voicelink: scan timed out\n");
      close(sock);
      return -ETIMEDOUT;
    }

  /* Collect scan results */

  memset(&list, 0, sizeof(list));
  ret = wapi_scan_coll(sock, VOICELINK_WIFI_IFNAME, &list);
  if (ret < 0)
    {
      syslog(LOG_ERR, "voicelink: scan_coll failed: %d\n", ret);
      close(sock);
      return ret;
    }

  /* Convert wapi results to voicelink_ap */

  for (info = list.head.scan; info != NULL && *count < capacity;
       info = info->next)
    {
      if (!info->has_essid || info->essid[0] == '\0')
        {
          continue; /* Skip hidden networks */
        }

      struct voicelink_ap *ap = &aps[*count];

      strncpy(ap->ssid, info->essid, sizeof(ap->ssid) - 1);
      ap->ssid[sizeof(ap->ssid) - 1] = '\0';

      ap->rssi = info->has_rssi ? info->rssi : -100;

      /* encode != 0 means some form of encryption is active */

      ap->secured = (info->has_encode && info->encode != 0) ? 1 : 0;

      (*count)++;
    }

  wapi_scan_coll_free(&list);
  close(sock);

  syslog(LOG_INFO, "voicelink: wifi scan found %zu APs\n", *count);
  return 0;
}

/****************************************************************************
 * voicelink_board_wifi_connect
 *
 * Connect to an access point using the NuttX wapi library.
 * password may be NULL for open networks.
 * NEVER log the password.
 ****************************************************************************/

int voicelink_board_wifi_connect(const char *ssid, const char *password,
                                 size_t password_len)
{
  struct wpa_wconfig_s conf;
  int sock;
  int ret;

  if (ssid == NULL || ssid[0] == '\0')
    {
      return -EINVAL;
    }

  if (password == NULL && password_len != 0)
    {
      return -EINVAL;
    }

  sock = wapi_make_socket();
  if (sock < 0)
    {
      syslog(LOG_ERR, "voicelink: wapi_make_socket failed: %d\n", sock);
      return sock;
    }

  /* Ensure the interface is up */

  ret = wapi_set_ifup(sock, VOICELINK_WIFI_IFNAME);
  if (ret < 0)
    {
      syslog(LOG_ERR, "voicelink: ifup %s failed: %d\n",
             VOICELINK_WIFI_IFNAME, ret);
      close(sock);
      return ret;
    }

  /* Build the wpa_wconfig_s structure */

  memset(&conf, 0, sizeof(conf));
  conf.ifname    = VOICELINK_WIFI_IFNAME;
  conf.sta_mode  = WAPI_MODE_MANAGED;
  conf.ssid      = ssid;
  conf.ssidlen   = strlen(ssid);
  conf.freq      = 0;
  conf.flag      = WAPI_FREQ_AUTO;
  conf.bssid     = NULL;

  if (password != NULL && password_len > 0)
    {
      /* WPA2-PSK with CCMP (most common). The wpa_driver_wext_associate
       * function handles key derivation from the passphrase. */

      conf.passphrase = password;
      conf.phraselen  = password_len;
      conf.alg        = WPA_ALG_CCMP;
      conf.auth_wpa   = IW_AUTH_WPA_VERSION_WPA2;
      conf.cipher_mode = IW_AUTH_CIPHER_CCMP;
    }
  else
    {
      /* Open network */

      conf.passphrase  = NULL;
      conf.phraselen   = 0;
      conf.alg         = WPA_ALG_NONE;
      conf.auth_wpa    = IW_AUTH_WPA_VERSION_DISABLED;
      conf.cipher_mode = IW_AUTH_CIPHER_NONE;
    }

  /* Associate. This function handles the full connect flow:
   * set auth params -> set key -> set essid -> wait for association.
   * Do NOT log the password. */

  ret = wpa_driver_wext_associate(&conf);

  close(sock);

  if (ret == 0)
    {
      syslog(LOG_INFO, "voicelink: wifi connected to %s\n", ssid);
      return VOICELINK_WIFI_OK;
    }

  /* Map error codes to our result enum.
   * The exact errno depends on the VS6621SR80 driver; common cases: */

  syslog(LOG_ERR, "voicelink: wifi_connect(%s) failed: %d\n", ssid, ret);

  if (ret == -EACCES || ret == -EPERM)
    {
      return VOICELINK_WIFI_WRONG_PASSWORD;
    }

  if (ret == -ETIMEDOUT)
    {
      return VOICELINK_WIFI_TIMEOUT;
    }

  if (ret == -ENOTCONN || ret == -ENOENT)
    {
      return VOICELINK_WIFI_NOT_FOUND;
    }

  return VOICELINK_WIFI_FAILED;
}

/****************************************************************************
 * voicelink_board_asr_next
 ****************************************************************************/

int voicelink_board_asr_next(enum voicelink_grammar grammar, char *utf8_text,
                              size_t capacity)
{
  if (utf8_text == NULL || capacity == 0)
    {
      return -EINVAL;
    }

  memset(utf8_text, 0, capacity);

  return voicelink_speech_recognize(grammar, utf8_text, capacity);
}
