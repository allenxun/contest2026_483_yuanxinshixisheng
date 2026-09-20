#include <pthread.h>
typedef pthread_mutex_t mutex_t;
extern int mock_lock_error;
static inline int nxmutex_init(mutex_t *m) { return pthread_mutex_init(m,0); }
static inline int nxmutex_lock(mutex_t *m) { return mock_lock_error ? mock_lock_error : pthread_mutex_lock(m); }
static inline int nxmutex_unlock(mutex_t *m) { return pthread_mutex_unlock(m); }
