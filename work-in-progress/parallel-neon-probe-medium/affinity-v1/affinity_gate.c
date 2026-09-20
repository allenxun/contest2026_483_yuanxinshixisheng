#include "affinity_gate.h"
#include <errno.h>
static int record(struct vv_affinity_gate *g, int error) {
    int expected = 0;
    if (error) atomic_compare_exchange_strong(&g->error, &expected, error);
    return error;
}
int vv_affinity_init(struct vv_affinity_gate *g, unsigned threads) {
    if (!g || threads < 1 || threads > 4) return EINVAL;
    g->threads = threads;
    atomic_init(&g->ready, 0);
    atomic_init(&g->error, 0);
    for (unsigned i = 0; i < 4; ++i) atomic_init(&g->observed[i], -1);
    return 0;
}
int vv_affinity_attr(struct vv_affinity_gate *g, const struct vv_affinity_ops *o,
                     void *attr, unsigned index) {
    if (!g || !o || !o->attr_cpu || !attr || index >= g->threads) return EINVAL;
    return record(g, o->attr_cpu(o->ctx, attr, 4 + index));
}
int vv_affinity_observe(struct vv_affinity_gate *g, const struct vv_affinity_ops *o,
                        unsigned index, int startup) {
    if (!g || !o || !o->current_cpu || index >= g->threads) return EINVAL;
    int cpu = -1;
    int rc = o->current_cpu(o->ctx, &cpu);
    atomic_store(&g->observed[index], rc ? -1 : cpu);
    if (!rc && cpu != (int)(4 + index)) rc = EXDEV;
    record(g, rc);
    if (startup) atomic_fetch_or(&g->ready, 1u << index);
    return rc;
}
int vv_affinity_ready(const struct vv_affinity_gate *g) {
    if (!g) return EINVAL;
    int rc = atomic_load(&g->error);
    if (rc) return rc;
    return atomic_load(&g->ready) == ((1u << g->threads) - 1u) ? 0 : EAGAIN;
}
int vv_affinity_result(const struct vv_affinity_gate *g) {
    return g ? atomic_load(&g->error) : EINVAL;
}
