#ifndef VV_AFFINITY_GATE_H
#define VV_AFFINITY_GATE_H
#include <stddef.h>
#include <stdatomic.h>
/* A fixed four-slot admission/observation adapter, NOT a thread pool. */
struct vv_affinity_ops {
    void *ctx;
    int (*attr_cpu)(void *ctx, void *pthread_attr, unsigned cpu);
    int (*current_cpu)(void *ctx, int *cpu); /* errno code; no fake CPU */
};
struct vv_affinity_gate {
    unsigned threads;
    atomic_uint ready;
    atomic_int error;
    atomic_int observed[4];
};
int vv_affinity_init(struct vv_affinity_gate *, unsigned threads);
int vv_affinity_attr(struct vv_affinity_gate *, const struct vv_affinity_ops *,
                     void *attr, unsigned index);
int vv_affinity_observe(struct vv_affinity_gate *, const struct vv_affinity_ops *,
                        unsigned index, int startup);
/* EAGAIN means outstanding startup observations; all other errors terminal. */
int vv_affinity_ready(const struct vv_affinity_gate *);
int vv_affinity_result(const struct vv_affinity_gate *);
/* Only implemented by affinity_nuttx.c on NuttX. */
const struct vv_affinity_ops *vv_affinity_nuttx_ops(void);
#endif
