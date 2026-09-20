#include "k7_arena_diagnostic.h"
#include <nuttx/mm/k7_model_arena.h>
#include "mock.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);return 1;}}while(0)
static struct kap_state state;
int main(int argc,char **argv){
    struct kap_report r;int mode,rc;CHECK(argc==2);mode=atoi(argv[1]);kap_mock_mode(mode);
    if(mode==6){
        struct k7_buft_provider p;CHECK(kap_initialize(&state)==0);p=kap_provider(&state);
        CHECK(!p.allocate(p.context,KAP_LIMIT+64,64) && kap_mock_alloc_calls()==0);
        CHECK(!p.allocate(p.context,64,128) && kap_mock_alloc_calls()==0);
        CHECK(kap_initialize(&state)==-EBUSY);
        puts("PASS cap/alignment rejected before API; invalid state cannot restart");return 0;
    }
    if(mode==7){
        struct k7_buft_provider p;void *a;CHECK(kap_initialize(&state)==0);p=kap_provider(&state);
        a=p.allocate(p.context,KAP_LIMIT,64);CHECK(a && kap_range_valid(a,KAP_LIMIT));
        CHECK(!p.allocate(p.context,64,64) && kap_mock_alloc_calls()==1);
        p.release(p.context,a,KAP_LIMIT);CHECK(kap_mock_free_calls()==1 && kap_live_slots(&state)==0);
        puts("PASS exact 1MiB mock boundary, aggregate overflow denied, paired release");return 0;
    }
    if(mode==8){
        struct k7_buft_provider p;void *a;CHECK(kap_initialize(&state)==0);p=kap_provider(&state);
        a=p.allocate(p.context,64,64);CHECK(a);
        p.release(p.context,a,128);CHECK(kap_mock_free_calls()==0 && kap_live_slots(&state)==1);
        p.release(p.context,a,64);CHECK(kap_mock_free_calls()==1);
        p.release(p.context,a,64);CHECK(kap_mock_free_calls()==1);
        puts("PASS mismatched/double release never reaches target free");return 0;
    }
    rc=kap_diagnostic(&state,&r);
    if(mode==0)CHECK(rc==0 && r.values_checked==8192 && !r.mismatches && r.addresses_valid && r.returned_to_baseline && r.allocations==r.releases && !r.live_slots);
    if(mode==1)CHECK(rc!=0 && r.initialize_status==-ENOMEM && kap_mock_alloc_calls()==0 && !state.ready);
    if(mode==2)CHECK(rc==ENOMEM && r.returned_to_baseline && !r.live_slots);
    if(mode==3 || mode==4)CHECK(rc!=0 && r.quarantined==1 && r.live_slots==1 && kap_mock_free_calls()==0 && kap_initialize(&state)==-EBUSY);
    if(mode==5)CHECK(rc!=0 && !r.returned_to_baseline && r.errors && kap_initialize(&state)==-EBUSY);
    printf("PASS mode=%d result=%d init_raw=%d checked=%u before=%zu after=%zu peak=%zu live=%u quarantine=%u releases=%u\n",mode,rc,r.initialize_status,r.values_checked,r.available_before,r.available_after,r.peak_bytes,r.live_slots,r.quarantined,r.releases);
    return 0;
}
