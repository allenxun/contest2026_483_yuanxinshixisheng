typedef int mutex_t;
#define NXMUTEX_INITIALIZER 0
static int nxmutex_trylock(mutex_t *m) { if (*m) return -16; *m=1; return 0; }
static int nxmutex_unlock(mutex_t *m) { *m=0; return 0; }
