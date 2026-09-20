#ifndef K7_RADIO_SERVICE_H
#define K7_RADIO_SERVICE_H
#include "wifi_scan.h"
/* Returned after explicit wifi-service-start succeeds; no backend fallback.
 * Returned service lives for the process lifetime. Never mutate its fields. */
struct k7wd_dispatch *k7_wifi_dispatch(void);
struct ws_service *k7_wifi_scans(void);
#endif
