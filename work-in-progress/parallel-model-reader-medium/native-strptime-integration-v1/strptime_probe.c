/* Target-side link/runtime probe candidate, not run here. */
#include <time.h>
#include <string.h>
#ifndef CONFIG_ALLOW_MIT_COMPONENTS
# error "Real NuttX MIT component configuration is required"
#endif
int k7_strptime_probe(void)
{
  struct tm t;
  char *end;
  memset(&t, 0, sizeof(t));
  end = strptime("2024-02-29 13:45:06tail", "%Y-%m-%d %H:%M:%S", &t);
  if (!end || strcmp(end, "tail") || t.tm_year != 124 || t.tm_mon != 1 ||
      t.tm_mday != 29 || t.tm_hour != 13 || t.tm_min != 45 || t.tm_sec != 6)
    return 1;
  memset(&t, 0, sizeof(t));
  if (strptime("13", "%m", &t) != 0) return 2;
  memset(&t, 0, sizeof(t));
  if (strptime("xx", "%Y", &t) != 0) return 3;
  return 0;
}
