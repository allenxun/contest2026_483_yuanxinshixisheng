#include "affinity_gate.h"
#include <errno.h>
#include <stdio.h>
struct mock {int attr_error, cpu_error, cpu; unsigned calls, requested;};
static int attr(void *ctx, void *p, unsigned cpu) {
    struct mock *m = ctx; (void)p; m->calls++; m->requested = cpu; return m->attr_error;
}
static int current(void *ctx, int *cpu) {
    struct mock *m = ctx; *cpu = m->cpu; return m->cpu_error;
}
#define CHECK(x) do { ++checks; if (!(x)) {printf("FAIL line=%d\n",__LINE__);return 1;} } while(0)
int main(void) {
    unsigned checks = 0; int dummy;
    struct mock m = {0};
    struct vv_affinity_ops ops = {&m, attr, current};
    struct vv_affinity_gate g;
    CHECK(vv_affinity_init(&g,0)==EINVAL);
    CHECK(vv_affinity_init(&g,5)==EINVAL);
    for (unsigned n=1;n<=4;n++) {
        CHECK(vv_affinity_init(&g,n)==0);
        CHECK(vv_affinity_ready(&g)==EAGAIN);
        for(unsigned i=0;i<n;i++) {
            CHECK(vv_affinity_attr(&g,&ops,&dummy,i)==0);
            CHECK(m.requested==4+i);
            m.cpu=4+(int)i;
            CHECK(vv_affinity_observe(&g,&ops,i,1)==0);
            CHECK(vv_affinity_ready(&g)==(i+1==n?0:EAGAIN));
        }
        CHECK(vv_affinity_result(&g)==0);
    }
    CHECK(vv_affinity_init(&g,4)==0);
    m.attr_error=EPERM;
    CHECK(vv_affinity_attr(&g,&ops,&dummy,1)==EPERM);
    CHECK(vv_affinity_ready(&g)==EPERM);
    m.attr_error=0; m.cpu=0;
    CHECK(vv_affinity_observe(&g,&ops,1,1)==EXDEV);
    CHECK(vv_affinity_result(&g)==EPERM); /* first error retained */
    CHECK(vv_affinity_init(&g,4)==0);
    m.cpu_error=EIO;
    CHECK(vv_affinity_observe(&g,&ops,0,1)==EIO);
    CHECK(atomic_load(&g.observed[0])==-1);
    CHECK(vv_affinity_ready(&g)==EIO);
    CHECK(vv_affinity_init(&g,1)==0);
    m.cpu_error=0; m.cpu=4;
    CHECK(vv_affinity_observe(&g,&ops,0,1)==0);
    CHECK(vv_affinity_ready(&g)==0);
    m.cpu=5;
    CHECK(vv_affinity_observe(&g,&ops,0,0)==EXDEV);
    CHECK(vv_affinity_result(&g)==EXDEV);
    unsigned calls=m.calls;
    CHECK(vv_affinity_attr(&g,&ops,&dummy,4)==EINVAL);
    CHECK(m.calls==calls);
    printf("mock affinity PASS checks=%u; no NuttX scheduling executed\n",checks);
    return 0;
}
