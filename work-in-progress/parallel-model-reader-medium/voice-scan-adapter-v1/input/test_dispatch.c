#include "wifi_dispatch.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static atomic_uint checks;
#define CHECK(x) do {atomic_fetch_add(&checks,1);if(!(x)){fprintf(stderr,"check_failed_line=%d\n",__LINE__);abort();}}while(0)
static const char secret[]="!WD.secret#123";
struct fixture {
 pthread_mutex_t queue,backend;
 atomic_uint_fast64_t clock;
 struct wd_dispatch d;struct wb_job job;
 unsigned submits,stops;bool reject;
};
static void lock(void *p){CHECK(pthread_mutex_lock(&((struct fixture *)p)->queue)==0);}
static void unlock(void *p){CHECK(pthread_mutex_unlock(&((struct fixture *)p)->queue)==0);}
static uint64_t now(void *p){return atomic_load(&((struct fixture *)p)->clock);}
static void outside_lock(struct fixture *f){CHECK(pthread_mutex_trylock(&f->queue)==0);CHECK(pthread_mutex_unlock(&f->queue)==0);}
static int submit(void *p,const struct wb_job *job){
 struct fixture *f=p;
 /* During concurrent tests another producer can legitimately hold the mutex;
  * reentrant queue API is the stronger deadlock test, performed every submit. */
 struct wd_view v;CHECK(wd_ble_poll(&f->d,UINT64_MAX,&v)==WD_UNKNOWN);
 CHECK(wd_pump(&f->d)==WD_BUSY);
 CHECK(pthread_mutex_lock(&f->backend)==0);++f->submits;
 CHECK(job->password_len==sizeof(secret)-1 && !memcmp(job->password,secret,sizeof(secret)-1));
 if(!f->reject)f->job=*job;
 CHECK(pthread_mutex_unlock(&f->backend)==0);return f->reject?-1:0;
}
static int stop(void *p,uint64_t owner,uint64_t id){
 struct fixture *f=p;CHECK(owner && id);++f->stops;
 struct wd_view v;CHECK(wd_voice_poll(&f->d,UINT64_MAX,&v)==WD_UNKNOWN);return 0;
}
static void init(struct fixture *f,bool offline){
 memset(f,0,sizeof(*f));CHECK(pthread_mutex_init(&f->queue,NULL)==0);CHECK(pthread_mutex_init(&f->backend,NULL)==0);
 atomic_init(&f->clock,1);struct wd_port port={f,lock,unlock,now,submit,stop};CHECK(wd_init(&f->d,&port,offline)==0);
}
static void end(struct fixture *f){wb_job_clear(&f->job);CHECK(pthread_mutex_destroy(&f->backend)==0);CHECK(pthread_mutex_destroy(&f->queue)==0);}
static enum wd_rc begin(struct fixture *f,bool ble,uint64_t *id){return ble?
 wd_ble_begin(&f->d,"mock",4,secret,sizeof(secret)-1,1000,id):wd_voice_begin(&f->d,"mock",4,secret,sizeof(secret)-1,1000,id);}
static struct wd_view view(struct fixture *f,bool ble,uint64_t id){struct wd_view v;CHECK((ble?wd_ble_poll(&f->d,id,&v):wd_voice_poll(&f->d,id,&v))==WD_OK);return v;}
static void pump(struct fixture *f){CHECK(wd_pump(&f->d)==WD_OK);}
static struct wd_event event(struct fixture *f,uint64_t sequence,enum wd_event_kind kind,bool success,bool exit,bool online){
 struct wd_event e;memset(&e,0,sizeof(e));e.kind=kind;e.done.owner=f->job.owner;e.done.id=f->job.id;
 e.done.sequence=sequence;e.done.success=success;e.done.authenticated=success;e.done.dhcp=success;e.done.worker_exited=exit;e.done.link_up=online;
 e.done.ip[0]=192;e.done.ip[1]=0;e.done.ip[2]=2;e.done.ip[3]=1;return e;
}
static void post(struct fixture *f,struct wd_event e){CHECK(wd_post(&f->d,&e)==WD_OK);pump(f);}
static void clean(struct fixture *f,uint64_t seq){struct wd_event e=event(f,seq,WD_COMPLETION,false,true,false);wb_job_clear(&f->job);post(f,e);}
struct caller {struct fixture *f;pthread_barrier_t *barrier;bool ble;unsigned rounds;uint64_t id;enum wd_rc rc;};
static void barrier(pthread_barrier_t *b){int rc=pthread_barrier_wait(b);CHECK(rc==0 || rc==PTHREAD_BARRIER_SERIAL_THREAD);}
static void *client(void *p){struct caller *c=p;for(unsigned i=0;i<c->rounds;i++){
 barrier(c->barrier);c->rc=begin(c->f,c->ble,&c->id);barrier(c->barrier);
 /* Actual clients read concurrently with owner processing and each other. */
 for(unsigned j=0;j<8;j++){struct wd_view v;CHECK((c->ble?wd_ble_poll(&c->f->d,c->id,&v):wd_voice_poll(&c->f->d,c->id,&v))==WD_OK);}
 barrier(c->barrier);
 }return NULL;}
struct publisher {struct fixture *f;struct wd_event *events;unsigned count;};
static void *publish_thread(void *p){struct publisher *pub=p;for(unsigned i=0;i<pub->count;i++)CHECK(wd_post(&pub->f->d,&pub->events[i])==WD_OK);return NULL;}
static void concurrent_rounds(void){
 struct fixture f;pthread_barrier_t b;pthread_t threads[2];struct caller c[2];init(&f,true);
 CHECK(pthread_barrier_init(&b,NULL,3)==0);
 for(unsigned i=0;i<2;i++){c[i]=(struct caller){&f,&b,i==0,200,0,WD_UNKNOWN};CHECK(pthread_create(&threads[i],NULL,client,&c[i])==0);}
 for(unsigned round=0;round<200;round++){
  barrier(&b);barrier(&b);CHECK(c[0].rc==WD_OK && c[1].rc==WD_OK && c[0].id!=c[1].id);
  pump(&f);pump(&f);barrier(&b);
  struct wd_view a=view(&f,true,c[0].id),v=view(&f,false,c[1].id);
  CHECK((a.status==WB_CONNECTING && v.status==WB_BUSY) || (v.status==WB_CONNECTING && a.status==WB_BUSY));
  bool ble=a.status==WB_CONNECTING;uint64_t ticket=ble?c[0].id:c[1].id;
  CHECK((ble?wd_voice_cancel(&f.d,ticket):wd_ble_cancel(&f.d,ticket))==WD_FORBIDDEN);
  CHECK((ble?wd_ble_cancel(&f.d,ticket):wd_voice_cancel(&f.d,ticket))==WD_OK);pump(&f);
  CHECK(view(&f,ble,ticket).status==WB_CANCELLED && view(&f,ble,ticket).held);
  struct wd_event e[3]={event(&f,1,WD_PROGRESS,true,false,true),event(&f,2,WD_COMPLETION,true,true,true),event(&f,3,WD_COMPLETION,false,true,false)};
  struct publisher pub={&f,e,3};pthread_t t;
  /* Copy release event before worker-owned credential cleanup. */
  wb_job_clear(&f.job);CHECK(pthread_create(&t,NULL,publish_thread,&pub)==0);
  /* Pump concurrently with backend event publisher; no busy waiting on network. */
  for(unsigned j=0;j<5;j++)pump(&f);
  CHECK(pthread_join(t,NULL)==0);for(unsigned j=0;j<3;j++)pump(&f);
  CHECK(view(&f,ble,ticket).status==WB_CANCELLED && !view(&f,ble,ticket).held);
  CHECK(f.d.broker.radio==WB_FREE);
 }
 for(unsigned i=0;i<2;i++)CHECK(pthread_join(threads[i],NULL)==0);
 CHECK(f.submits==200 && f.stops==200);CHECK(pthread_barrier_destroy(&b)==0);end(&f);
}
static bool has_secret(const void *ptr,size_t n){const unsigned char *b=ptr;for(size_t i=0;i+sizeof(secret)-1<=n;i++)if(!memcmp(b+i,secret,sizeof(secret)-1))return true;return false;}
static void *burst_client(void *p){
 struct caller *c=p;barrier(c->barrier);c->rc=begin(c->f,c->ble,&c->id);return NULL;
}
static void concurrent_full(void){
 struct fixture f;pthread_barrier_t b;pthread_t t[12];struct caller c[12];unsigned accepted=0,full=0;
 init(&f,true);CHECK(pthread_barrier_init(&b,NULL,13)==0);
 for(unsigned i=0;i<12;i++){c[i]=(struct caller){&f,&b,i%2==0,1,0,WD_UNKNOWN};CHECK(pthread_create(&t[i],NULL,burst_client,&c[i])==0);}
 barrier(&b);
 for(unsigned i=0;i<12;i++){
  CHECK(pthread_join(t[i],NULL)==0);CHECK(c[i].id!=0);
  for(unsigned j=0;j<i;j++){CHECK(c[j].id!=c[i].id);}
  if(c[i].rc==WD_OK){++accepted;CHECK((c[i].ble?wd_ble_cancel(&f.d,c[i].id):wd_voice_cancel(&f.d,c[i].id))==WD_OK);}
  else {CHECK(c[i].rc==WD_FULL);++full;}
 }
 CHECK(accepted==WD_REQUESTS && full==4);
 for(unsigned i=0;i<WD_REQUESTS;i++){pump(&f);}
 CHECK(f.submits==0 && !has_secret(&f.d,sizeof(f.d)));
 CHECK(pthread_barrier_destroy(&b)==0);end(&f);
}
static void targeted(void){
 struct fixture f;uint64_t id,retry;init(&f,true);CHECK(begin(&f,true,&id)==WD_OK);pump(&f);
 outside_lock(&f);CHECK(!has_secret(&f.d,sizeof(f.d)));CHECK(has_secret(&f.job,sizeof(f.job)));
 post(&f,event(&f,1,WD_PROGRESS,true,false,true));CHECK(view(&f,true,id).status==WB_CONNECTING);
 post(&f,event(&f,2,WD_COMPLETION,true,true,true));CHECK(view(&f,true,id).status==WB_IP_READY);
 CHECK(wd_ble_cancel(&f.d,id)==WD_OK);pump(&f);CHECK(view(&f,true,id).status==WB_IP_READY);
 CHECK(wd_voice_release(&f.d,id)==WD_FORBIDDEN);CHECK(wd_ble_release(&f.d,id)==WD_OK);pump(&f);
 CHECK(begin(&f,false,&retry)==WD_OK);pump(&f);CHECK(view(&f,false,retry).status==WB_BUSY);
 post(&f,event(&f,3,WD_COMPLETION,false,false,false));CHECK(view(&f,true,id).held);
 post(&f,event(&f,4,WD_COMPLETION,true,true,true));CHECK(view(&f,true,id).held);
 struct wd_event stale=event(&f,100,WD_COMPLETION,true,true,true);clean(&f,5);
 CHECK(!view(&f,true,id).held && !has_secret(&f.d,sizeof(f.d)));
 CHECK(begin(&f,false,&retry)==WD_OK);pump(&f);post(&f,stale);CHECK(view(&f,false,retry).status==WB_CONNECTING);
 CHECK(wd_voice_cancel(&f.d,retry)==WD_OK);pump(&f);clean(&f,1);end(&f);
 /* Full request queue: cancellation does not need another queue slot. */
 init(&f,true);uint64_t ids[WD_REQUESTS];
 for(unsigned i=0;i<WD_REQUESTS;i++)CHECK(begin(&f,true,&ids[i])==WD_OK);
 CHECK(begin(&f,false,&retry)==WD_FULL && retry!=0);
 for(unsigned i=0;i<WD_REQUESTS;i++)CHECK(wd_ble_cancel(&f.d,ids[i])==WD_OK);
 CHECK(!has_secret(f.d.requests,sizeof(f.d.requests)));
 for(unsigned i=0;i<WD_REQUESTS;i++)pump(&f);
 CHECK(f.submits==0);end(&f);
 /* Event queue full: backend retains final fence and retries unchanged. */
 init(&f,true);CHECK(begin(&f,true,&id)==WD_OK);pump(&f);CHECK(wd_ble_cancel(&f.d,id)==WD_OK);pump(&f);
 for(unsigned i=0;i<WD_EVENTS;i++){struct wd_event e=event(&f,i+1,WD_PROGRESS,true,false,true);CHECK(wd_post(&f.d,&e)==WD_OK);}
 struct wd_event exit=event(&f,WD_EVENTS+1,WD_COMPLETION,false,true,false);
 CHECK(wd_post(&f.d,&exit)==WD_FULL);pump(&f);CHECK(view(&f,true,id).held);
 CHECK(wd_post(&f.d,&exit)==WD_OK);wb_job_clear(&f.job);
 for(unsigned i=0;i<WD_EVENTS;i++){pump(&f);}
 CHECK(!view(&f,true,id).held);end(&f);
 /* Submission rejection has proof of no started worker, so may free. */
 init(&f,true);CHECK(begin(&f,true,&id)==WD_OK);pump(&f);
 post(&f,event(&f,1,WD_COMPLETION,true,true,true));CHECK(view(&f,true,id).status==WB_IP_READY);
 post(&f,event(&f,2,WD_COMPLETION,false,false,false));
 CHECK(view(&f,true,id).status==WB_FAILED && view(&f,true,id).held);
 CHECK(begin(&f,false,&retry)==WD_OK);pump(&f);CHECK(view(&f,false,retry).status==WB_BUSY);
 post(&f,event(&f,3,WD_COMPLETION,true,true,true));CHECK(view(&f,true,id).status==WB_FAILED && view(&f,true,id).held);
 clean(&f,4);CHECK(!view(&f,true,id).held);end(&f);
 /* Submission rejection has proof of no started worker, so may free. */
 init(&f,true);f.reject=true;CHECK(begin(&f,true,&id)==WD_OK);pump(&f);
 CHECK(view(&f,true,id).status==WB_FAILED && !view(&f,true,id).held);end(&f);
 /* Queue time counts in deadline and wipes without starting. */
 init(&f,true);CHECK(begin(&f,true,&id)==WD_OK);atomic_store(&f.clock,1001);pump(&f);
 CHECK(view(&f,true,id).status==WB_TIMEOUT && f.submits==0 && !has_secret(&f.d,sizeof(f.d)));end(&f);
 /* Running timeout retains ownership despite late IP and concurrent retry. */
 init(&f,true);CHECK(begin(&f,true,&id)==WD_OK);pump(&f);atomic_store(&f.clock,1001);pump(&f);
 CHECK(view(&f,true,id).status==WB_TIMEOUT && view(&f,true,id).held && f.stops==1);
 CHECK(begin(&f,false,&retry)==WD_OK);pump(&f);CHECK(view(&f,false,retry).status==WB_BUSY);
 post(&f,event(&f,2,WD_COMPLETION,true,true,true));CHECK(view(&f,true,id).status==WB_TIMEOUT && view(&f,true,id).held);
 post(&f,event(&f,1,WD_COMPLETION,false,true,false));CHECK(view(&f,true,id).held);
 clean(&f,3);CHECK(!view(&f,true,id).held);end(&f);
 /* Unproven legacy ownership never automatically frees on arbitrary events. */
 init(&f,false);CHECK(begin(&f,true,&id)==WD_OK);pump(&f);CHECK(view(&f,true,id).status==WB_BUSY && f.submits==0);end(&f);
}
int main(void){atomic_init(&checks,0);concurrent_rounds();concurrent_full();targeted();printf("actual_pthread_rounds=200 burst_clients=12 checks=%u failures=0 mock_backend_only\n",atomic_load(&checks));return 0;}
