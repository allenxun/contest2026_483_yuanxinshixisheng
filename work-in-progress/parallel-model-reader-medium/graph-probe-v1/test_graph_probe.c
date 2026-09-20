#include "graph_probe.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
static struct gp_state s;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL line=%d %s\n",__LINE__,#x);return 1;}}while(0)
static int clean(void) {
    struct gp_report r;gp_snapshot(&s,&r);
    return !s.pool&&!s.ctx&&!r.pool_bytes&&!r.handles&&!r.running&&!r.mutexes&&!r.conds&&!r.attrs&&r.starts==r.exits;
}
int main(int argc,char **argv) {
    struct gp_report r;int scenario,rc;unsigned threads;
    CHECK(argc==3);threads=(unsigned)atoi(argv[1]);scenario=atoi(argv[2]);gp_initialize(&s);
    if(scenario==1){s.fail_site=POOL_ALLOC;s.fail_ordinal=1;}
    if(scenario==2){s.fail_site=THREAD_CREATE;s.fail_ordinal=threads-1;}
    if(scenario==3){s.fail_site=THREAD_CREATE;s.fail_ordinal=threads-1;s.fail_join=1;}
    if(scenario>=4 && scenario<=8)s.fail_stage=scenario-3;
    if(scenario==9)s.fail_join=1;
    rc=gp_run(&s,threads);gp_snapshot(&s,&r);
    if(scenario==0) {
        CHECK(rc==0 && r.checked_values==4096 && !r.mismatches);
        CHECK(r.worker_mask==((1u<<threads)-2u));
        CHECK(r.starts==threads-1 && r.exits==threads-1 && clean());
    } else if((scenario==3 && threads==4) || scenario==9) {
        CHECK(rc!=0 && s.pool && r.handles>0 && r.pool_bytes>0);
        if(scenario==9)CHECK(s.ctx && r.checked_values==4096);
        CHECK(gp_run(&s,threads)==EBUSY); /* Must not reuse live hooks/storage. */
        s.fail_join=0;CHECK(gp_cleanup(&s)==0 && clean());
    } else {CHECK(rc!=0 && clean());}
    CHECK(gp_cleanup(&s)==0 && clean());
    printf("PASS scenario=%d threads=%u result=%d compute=%d checked=%u mismatches=%u mask=%u starts=%u exits=%u retained_before_retry=%d\n",
           scenario,threads,rc,r.compute_status,r.checked_values,r.mismatches,r.worker_mask,r.starts,r.exits,r.retained_pool);
    return 0;
}
