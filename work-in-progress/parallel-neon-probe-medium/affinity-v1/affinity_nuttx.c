/* This translation unit is not built/executed by host tests. APIs observed
 * in app/k7load and app/k7neon; NuttX headers/config remain integration gates. */
#ifndef __NuttX__
#error "NuttX affinity adapter must not be built as a host success stub"
#endif
#include <nuttx/config.h>
#include <pthread.h>
#include <sched.h>
#include <errno.h>
#include "affinity_gate.h"
#if !defined(CONFIG_SMP) || CONFIG_SMP_NCPUS < 8
#error "This fixed topology candidate requires the audited eight-CPU build"
#endif
static int attr_cpu(void *ctx, void *attr, unsigned cpu) {
    (void)ctx;
    if (!attr || cpu < 4 || cpu > 7) return EINVAL;
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    /* POSIX pthread API returns errno directly; DO NOT replace with errno. */
    return pthread_attr_setaffinity_np((pthread_attr_t *)attr, sizeof(set), &set);
}
static int current_cpu(void *ctx, int *cpu) {
    (void)ctx;
    errno = 0;
    int actual = sched_getcpu();
    if (actual < 0) return errno ? errno : EIO;
    *cpu = actual;
    return 0;
}
const struct vv_affinity_ops *vv_affinity_nuttx_ops(void) {
    static const struct vv_affinity_ops ops = {NULL, attr_cpu, current_cpu};
    return &ops;
}
