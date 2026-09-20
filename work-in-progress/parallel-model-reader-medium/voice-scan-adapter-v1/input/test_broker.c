#include "wifi_broker.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
static int checks, failures;
#define CHECK(x) do { ++checks; if(!(x)) {++failures; fprintf(stderr,"line %d: %s\n",__LINE__,#x);} }while(0)
static struct wb_result begin(struct wb_broker* b, uint64_t owner, uint64_t now) {
  return wb_begin(b,owner,"TestNet",7,"testpass",8,now,100);
}
static int zeroed(const void* p, size_t n) {
  const unsigned char* s=p; while(n--) if(*s++) return 0; return 1;
}
/* A deterministic worker mailbox; no network, threads or device access. */
struct fake_backend { struct wb_job job; unsigned starts; };
static void start(struct wb_broker* b, struct fake_backend* f, uint64_t now) {
  if(wb_take_job(b,&f->job,now)) ++f->starts;
}
static struct wb_done done(struct wb_result r, uint64_t seq, int success, int exited, int up) {
  struct wb_done d; memset(&d,0,sizeof(d)); d.owner=r.owner;d.id=r.id;d.sequence=seq;
  d.success=success;d.authenticated=success;d.dhcp=success;d.worker_exited=exited;d.link_up=up;
  d.ip[0]=192;d.ip[1]=0;d.ip[2]=2;d.ip[3]=7;return d;
}
static void contention(void) {
  struct wb_broker b; struct fake_backend f={0}; struct wb_result a,r; struct wb_done d;
  wb_init(&b,0,1); a=begin(&b,1,0); r=begin(&b,2,0);
  CHECK(a.status==WB_RECEIVED && r.status==WB_BUSY && r.id>a.id);
  CHECK(f.starts==0 && b.radio==WB_QUEUED);
  CHECK(wb_poll(&b,2,a.id).status==WB_UNKNOWN);
  wb_cancel(&b,2,a.id,0); CHECK(b.radio==WB_QUEUED);
  start(&b,&f,1); CHECK(f.starts==1);CHECK(zeroed(&b.pending,sizeof(b.pending)));
  CHECK(!memcmp(f.job.password,"testpass",8));
  start(&b,&f,1); CHECK(f.starts==1);
  d=done(a,1,1,1,1);d.owner=2;wb_complete(&b,&d,1);CHECK(b.radio==WB_RUNNING);
  /* BLE transport disconnect intentionally has no broker call. */
  wb_tick(&b,2); CHECK(b.radio==WB_RUNNING);
  d=done(a,2,1,1,1); wb_job_clear(&f.job); wb_complete(&b,&d,3);
  CHECK(zeroed(&f.job,sizeof(f.job))); CHECK(b.radio==WB_OWNED);
  CHECK(wb_poll(&b,1,a.id).status==WB_IP_READY);
  d=done(a,1,0,1,0); wb_complete(&b,&d,4); CHECK(b.radio==WB_OWNED);
  wb_cancel(&b,1,a.id,5);CHECK(b.radio==WB_OWNED);
  CHECK(begin(&b,2,5).status==WB_BUSY); CHECK(begin(&b,1,5).status==WB_BUSY);
  CHECK(!wb_release(&b,2,a.id,5)); CHECK(wb_release(&b,1,a.id,5));
  CHECK(wb_stop_requested(&b,1,a.id)); CHECK(begin(&b,2,6).status==WB_BUSY);
  d=done(a,3,0,1,0);wb_complete(&b,&d,7);CHECK(b.radio==WB_FREE);
  r=begin(&b,2,8);CHECK(r.status==WB_RECEIVED);
  d=done(a,4,1,1,1);wb_complete(&b,&d,9);CHECK(b.active.id==r.id && b.radio==WB_QUEUED);
}
static void drain_paths(void) {
  int mode;
  for(mode=0;mode<4;mode++) {
    struct wb_broker b;struct fake_backend f={0};struct wb_result a;struct wb_done d;
    uint64_t now=mode==1?100:2;
    wb_init(&b,0,1); a=begin(&b,1,0); start(&b,&f,1);
    if(mode==0) wb_cancel(&b,1,a.id,now);
    if(mode==1) wb_tick(&b,now);
    if(mode==2) {d=done(a,1,0,0,0);wb_complete(&b,&d,now);}
    if(mode==3) {d=done(a,1,0,1,1);wb_complete(&b,&d,now);}
    CHECK(b.radio==WB_DRAINING); CHECK(wb_stop_requested(&b,1,a.id));
    CHECK(begin(&b,2,now).status==WB_BUSY);
    d=done(a,2,1,1,1);wb_complete(&b,&d,now);CHECK(b.radio==WB_DRAINING);
    d=done(a,1,0,1,0);wb_complete(&b,&d,now);CHECK(b.radio==WB_DRAINING);
    CHECK(wb_poll(&b,1,a.id).status!=WB_IP_READY);
    d=done(a,3,0,0,0);wb_complete(&b,&d,now);CHECK(b.radio==WB_DRAINING);
    wb_job_clear(&f.job);d=done(a,4,0,1,0);wb_complete(&b,&d,now);
    CHECK(b.radio==WB_FREE);CHECK(begin(&b,2,now).status==WB_RECEIVED);
  }
}
static void queue_and_credentials(void) {
  int mode;
  for(mode=0;mode<3;mode++) {
    struct wb_broker b;struct wb_result a;struct wb_job j={0};char pw[]="testpass";
    wb_init(&b,0,1); a=wb_begin(&b,1,"TestNet",7,pw,8,0,100);memset(pw,'x',8);
    CHECK(!memcmp(b.pending.password,"testpass",8));
    if(mode==0) wb_cancel(&b,1,a.id,1);
    if(mode==1) wb_tick(&b,100);
    if(mode==2) wb_start_failed(&b,1,a.id,1);
    CHECK(b.radio==WB_FREE);CHECK(zeroed(&b.pending,sizeof(b.pending)));
    CHECK(!wb_take_job(&b,&j,mode==1?100:1));CHECK(zeroed(&j,sizeof(j)));
  }
}
static void false_success(void) {
  int mode;
  for(mode=0;mode<8;mode++) {
    struct wb_broker b;struct fake_backend f={0};struct wb_result a;struct wb_done d;
    wb_init(&b,0,1);a=begin(&b,1,0);d=done(a,1,1,1,1);
    wb_complete(&b,&d,0);CHECK(b.radio==WB_QUEUED); /* completion before start */
    start(&b,&f,0);
    if(mode==0)d.authenticated=0;
    if(mode==1)d.dhcp=0;
    if(mode==2)d.worker_exited=0;
    if(mode==3)d.link_up=0;
    if(mode==4)d.ip[0]=0;
    if(mode==5)d.ip[0]=127;
    if(mode==6)d.ip[0]=224;
    if(mode==7){d.ip[0]=169;d.ip[1]=254;}
    wb_complete(&b,&d,1);CHECK(wb_poll(&b,1,a.id).status==WB_FAILED);
    CHECK(b.radio==(d.worker_exited && !d.link_up?WB_FREE:WB_DRAINING));wb_job_clear(&f.job);
  }
}
static void boundaries(void) {
  struct wb_broker b; struct wb_result a,r;struct fake_backend f={0};struct wb_done d;int i;
  wb_init(&b,0,0);CHECK(begin(&b,1,0).status==WB_BUSY);wb_external_idle(&b);CHECK(b.radio==WB_FREE);
  CHECK(wb_begin(&b,1,"x",1,NULL,0,0,100).status==WB_UNSUPPORTED);
  CHECK(wb_begin(&b,0,"x",1,"testpass",8,0,100).status==WB_INVALID);
  CHECK(wb_begin(&b,1,"x",33,"testpass",8,0,100).status==WB_INVALID);
  CHECK(wb_begin(&b,1,"x",1,NULL,8,0,100).status==WB_INVALID);
  CHECK(wb_begin(&b,1,"x",1,"short",5,0,100).status==WB_INVALID);
  CHECK(wb_begin(&b,1,"x",1,"testpass",8,0,0).status==WB_INVALID);
  a=begin(&b,1,0);start(&b,&f,0);wb_start_failed(&b,1,a.id,0);CHECK(b.radio==WB_RUNNING);
  for(i=0;i<20;i++)CHECK(begin(&b,2,0).status==WB_BUSY);
  CHECK(wb_poll(&b,1,a.id).status==WB_CONNECTING);CHECK(wb_poll(&b,1,1).status==WB_UNKNOWN);
  d=done(a,1,1,1,1);wb_complete(&b,&d,100);CHECK(b.radio==WB_DRAINING && b.active.status==WB_TIMEOUT);
  wb_job_clear(&f.job);
  wb_init(&b,UINT64_MAX-10,1);a=wb_begin(&b,1,"x",1,"testpass",8,UINT64_MAX-10,20);
  wb_tick(&b,UINT64_MAX);CHECK(b.radio==WB_QUEUED);wb_tick(&b,0);
  CHECK(b.radio==WB_FREE && b.clock_fault);CHECK(wb_poll(&b,1,a.id).status==WB_CLOCK_ERROR);
  CHECK(begin(&b,2,0).status==WB_CLOCK_ERROR);
  wb_init(&b,10,1);a=begin(&b,1,10);start(&b,&f,10);wb_tick(&b,9);
  CHECK(b.radio==WB_DRAINING && b.active.status==WB_CLOCK_ERROR);wb_job_clear(&f.job);
  wb_init(&b,0,1);b.next_id=UINT64_MAX-1;
  a=begin(&b,1,0);r=begin(&b,2,0);CHECK(a.id==UINT64_MAX-1 && r.id==UINT64_MAX && r.status==WB_BUSY);
  r=begin(&b,2,0);CHECK(r.id==0 && r.status==WB_EXHAUSTED);CHECK(b.active.id==a.id);
  wb_cancel(&b,1,a.id,0);CHECK(begin(&b,1,0).status==WB_EXHAUSTED);
}
static void generated_sequences(void) {
  struct wb_broker b; uint32_t seed=3576; uint64_t now=0; int i;
  wb_init(&b,now,1);
  for(i=0;i<5000;i++) {
    uint64_t owner,id; enum wb_radio previous;
    seed=seed*1664525u+1013904223u; now+=seed%3;
    wb_tick(&b,now); previous=b.radio; owner=b.active.owner;id=b.active.id;
    switch((seed>>16)%6) {
      case 0: {
        struct wb_result r=begin(&b,(seed&1)+1,now);
        CHECK((r.status==WB_RECEIVED)==(previous==WB_FREE));
        if(previous!=WB_FREE) CHECK(b.active.id==id);
        break;
      }
      case 1: {
        struct wb_job j={0};int took=wb_take_job(&b,&j,now);
        CHECK(took==(previous==WB_QUEUED));wb_job_clear(&j);break;
      }
      case 2: wb_cancel(&b,owner,id,now);break;
      case 3: {
        struct wb_result r=b.active;
        struct wb_done d=done(r,b.event_sequence+1,(seed&1)!=0,1,(seed&1)!=0);
        wb_complete(&b,&d,now);break;
      }
      case 4: (void)wb_release(&b,owner,id,now);break;
      case 5: {
        struct wb_done d=done(b.active,b.event_sequence+1,1,1,1);d.id=UINT64_MAX;
        wb_complete(&b,&d,now);CHECK(b.radio==previous && b.active.id==id);break;
      }
    }
    if(b.radio!=WB_QUEUED)CHECK(zeroed(&b.pending,sizeof(b.pending)));
    if(b.radio==WB_OWNED)CHECK(b.active.status==WB_IP_READY);
    if(b.radio==WB_DRAINING)CHECK(b.active.status!=WB_IP_READY && b.active.status!=WB_CONNECTING);
    if(b.radio==WB_FREE)CHECK(b.active.id==0);
  }
}
int main(void) {
  contention();drain_paths();queue_and_credentials();false_success();boundaries();generated_sequences();
  printf("broker assertions=%d failures=%d\n",checks,failures);return failures?EXIT_FAILURE:EXIT_SUCCESS;
}
