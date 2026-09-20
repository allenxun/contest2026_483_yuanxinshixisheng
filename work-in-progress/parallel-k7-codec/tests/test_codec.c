#include "codec_txn.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
static unsigned checks;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
enum fault { NONE,IOERR,SHORT0,SHORT1,LONG3,WRONG_COUNTS,TIMEOUT,CANCEL,READBAD,EARLY_DELAY,REENTER,BACKWARD };
struct fake {
 struct kc_context *codec;uint64_t now;
 unsigned calls,target,reads,writes,delays,clocks,powers,prepares,cleanup_calls;
 enum fault fault;int cleanup_error;bool cleanup_late,cleanup_back;
 uint8_t regs[256];
};
static uint64_t now(void *ctx){return ((struct fake *)ctx)->now;}
static bool hit(struct fake *f){
 ++f->calls;
 if(f->calls!=f->target)return false;
 if(f->fault==TIMEOUT)f->now=f->codec->deadline;
 if(f->fault==BACKWARD)f->now=0;
 if(f->fault==CANCEL)CHECK(kc_cancel(f->codec,f->codec->id)==KC_OK);
 if(f->fault==REENTER){
  uint64_t id=0;
  CHECK(kc_poll(f->codec)==KC_BUSY);
  CHECK(kc_start(f->codec,&f->codec->plan,f->now+100,&id)==KC_BUSY);
  CHECK(kc_stop(f->codec,f->codec->id)==KC_BUSY);
  CHECK(kc_cleanup(f->codec,f->codec->id,f->now+100)==KC_BUSY);
 }
 return true;
}
static struct kc_io_result io_result(struct fake *f,bool inject,bool read){
 if(inject){
  if(f->fault==IOERR)return (struct kc_io_result){-5,0,0};
  if(f->fault==SHORT0)return (struct kc_io_result){0,0,0};
  if(f->fault==SHORT1)return (struct kc_io_result){0,1,0};
  if(f->fault==LONG3)return read?(struct kc_io_result){0,1,2}:(struct kc_io_result){0,3,0};
  if(f->fault==WRONG_COUNTS)return read?(struct kc_io_result){0,2,0}:(struct kc_io_result){0,1,1};
 }
 return read?(struct kc_io_result){0,1,1}:(struct kc_io_result){0,2,0};
}
static struct kc_io_result write_bus(void *ctx,uint8_t addr,const uint8_t *data,size_t n,uint64_t deadline){
 struct fake *f=ctx;bool inject;CHECK(addr==0x10 && n==2 && deadline==f->codec->deadline);
 ++f->writes;inject=hit(f);f->regs[data[0]]=data[1]; /* partial mutation even on failure */
 return io_result(f,inject,false);
}
static struct kc_io_result read_bus(void *ctx,uint8_t addr,uint8_t reg,uint8_t *value,uint64_t deadline){
 struct fake *f=ctx;bool inject;CHECK(addr==0x10 && deadline==f->codec->deadline);
 ++f->reads;inject=hit(f);*value=f->regs[reg];if(inject && f->fault==READBAD)*value^=1;
 return io_result(f,inject,true);
}
static int delay(void *ctx,uint32_t ms,uint64_t deadline){
 struct fake *f=ctx;bool inject;CHECK(ms && deadline==f->codec->deadline);++f->delays;
 inject=hit(f);if(!(inject && (f->fault==EARLY_DELAY || f->fault==BACKWARD)))f->now+=ms;
 return inject && f->fault==IOERR?-110:0;
}
static int clock_ready(void *ctx,uint32_t rate,uint32_t mclk,uint32_t bclk,uint64_t deadline){
 struct fake *f=ctx;CHECK(rate==16000 && mclk==4096000 && bclk==512000 && deadline==f->codec->deadline);
 ++f->clocks;return hit(f) && f->fault==IOERR?-5:0;
}
static int control(void *ctx,enum kc_control op,uint64_t id,uint64_t deadline){
 struct fake *f=ctx;CHECK(id==f->codec->id);
 if(op==KC_QUIESCE){++f->cleanup_calls;if(f->cleanup_late)f->now=deadline;
  if(f->cleanup_back)f->now=0;
  return f->cleanup_error;
 }
 if(op==KC_POWER_PREPARE)++f->powers;else if(op==KC_CAPTURE_PREPARE)++f->prepares;else CHECK(false);
 return hit(f) && f->fault==IOERR?-5:0;
}
static struct kc_plan plan(void){
 struct kc_plan p;kc_es8388_reference(&p);p.mode=KC_SIMULATION;p.reviews=KC_REVIEW_ALL;
 p.count=6;p.read_count=1;
 /* Synthetic register model, NOT codec configuration or readable-bit proof. */
 p.steps[0]=(struct kc_step){KC_WRITE,KC_INIT,KC_SIM_ONLY,900,0x20,0x11,0,0};
 p.steps[1]=(struct kc_step){KC_READ_VERIFY,KC_INIT,KC_SIM_ONLY,900,0x20,0x11,0x1f,0};
 p.steps[2]=(struct kc_step){KC_DELAY,KC_INIT,KC_SIM_ONLY,900,0,0,0,2};
 p.steps[3]=(struct kc_step){KC_WRITE,KC_CAPTURE,KC_SIM_ONLY,900,0x20,0x02,0,0};
 p.steps[4]=(struct kc_step){KC_READ_VERIFY,KC_CAPTURE,KC_SIM_ONLY,900,0x20,0x02,0x1f,0};
 p.steps[5]=(struct kc_step){KC_DELAY,KC_CAPTURE,KC_SIM_ONLY,900,0,0,0,3};
 p.reads[0]=(struct kc_read_rule){0x20,0x1f,KC_SIM_ONLY,900};return p;
}
static void init(struct kc_context *c,struct fake *f){
 struct kc_port port={f,now,write_bus,read_bus,delay,clock_ready,control,KC_SIMULATION};
 memset(f,0,sizeof(*f));f->codec=c;f->now=10;CHECK(kc_init(c,&port)==KC_OK);
}
static enum kc_status run(struct kc_context *c){
 enum kc_status s=KC_PENDING;unsigned limit=20;
 while(s==KC_PENDING && limit--)s=kc_poll(c);
 CHECK(limit>0);return s;
}
static void start(struct kc_context *c,struct kc_plan *p){uint64_t id=0;CHECK(kc_start(c,p,c->port.now_ms(c->port.ctx)+90,&id)==KC_PENDING);CHECK(id==c->id);}
int main(void){
 struct kc_context c;struct fake f;struct kc_plan p;uint64_t id;
 init(&c,&f);kc_es8388_reference(&p);id=777;
 CHECK(kc_start(&c,&p,100,&id)==KC_NOT_READY);CHECK(id==777 && f.calls==0 && c.state==KC_OFF);
 p=plan();start(&c,&p);p.steps[0].value=0xff; /* owned snapshot unaffected */
 CHECK(run(&c)==KC_OK && c.state==KC_READY);CHECK(f.calls==9 && f.writes==2 && f.reads==2);
 CHECK(kc_start(&c,&p,100,&id)==KC_BUSY);CHECK(kc_stop(&c,c.id)==KC_PENDING);
 f.cleanup_error=-16;CHECK(kc_cleanup(&c,c.id,200)==KC_IO && c.state==KC_STOPPING);
 CHECK(kc_start(&c,&p,200,&id)==KC_BUSY);CHECK(kc_cleanup(&c,c.id+1,200)==KC_STALE);
 f.cleanup_error=0;CHECK(kc_cleanup(&c,c.id,200)==KC_OK && c.state==KC_OFF);
 p=plan();start(&c,&p);CHECK(c.id==2);CHECK(kc_cancel(&c,1)==KC_STALE);
 CHECK(kc_cancel(&c,2)==KC_OK);CHECK(kc_poll(&c)==KC_CANCELLED);
 CHECK(kc_cleanup(&c,2,200)==KC_OK);
 /* Every control/clock/read/write/delay call: failure, late return, cancellation,
  * backwards clock, reentrant invocation. Each run contains nine accesses. */
 for(unsigned target=1;target<=9;target++)for(unsigned fault=IOERR;fault<=BACKWARD;fault++){
  bool bus=target==3 || target==4 || target==6 || target==7;
  bool read=target==4 || target==7,wait=target==5 || target==8;
  enum kc_status got;
  if((fault==SHORT0 || fault==SHORT1 || fault==LONG3 || fault==WRONG_COUNTS) && !bus)continue;
  if(fault==READBAD && !read)continue;
  if(fault==EARLY_DELAY && !wait)continue;
  init(&c,&f);p=plan();f.target=target;f.fault=(enum fault)fault;start(&c,&p);got=run(&c);
  if(fault==REENTER){CHECK(got==KC_OK);CHECK(kc_stop(&c,c.id)==KC_PENDING);}
  else {
   CHECK(got!=KC_OK && c.state==KC_STOPPING);CHECK(f.calls==target);
   CHECK(kc_poll(&c)==got && f.calls==target);
   if(fault==TIMEOUT)CHECK(got==KC_TIMEOUT);
   if(fault==CANCEL)CHECK(got==KC_CANCELLED);
   if(fault==SHORT0 || fault==SHORT1 || fault==LONG3 || fault==WRONG_COUNTS)CHECK(got==KC_SHORT);
   if(fault==READBAD)CHECK(got==KC_READBACK);
   if(fault==EARLY_DELAY)CHECK(got==KC_DELAY_ERROR);
   if(fault==BACKWARD)CHECK(got==KC_CLOCK);
   if(fault==IOERR)CHECK(c.port_error!=0 && c.failed_phase!=KC_PHASE_NONE);
  }
  f.fault=NONE;CHECK(kc_cleanup(&c,c.id,f.now+100)==KC_OK);
  if(fault==IOERR)CHECK(c.port_error!=0 && c.cleanup_port_error==0);
  if(c.state==KC_ERROR){
   if(c.clock_fault){CHECK(kc_reset_error(&c)==KC_NOT_READY);continue;}
   CHECK(kc_reset_error(&c)==KC_OK);
  }
  start(&c,&p);CHECK(run(&c)==KC_OK);CHECK(kc_stop(&c,c.id)==KC_PENDING);
  CHECK(kc_cleanup(&c,c.id,f.now+100)==KC_OK);
 }
 /* Configuration/readback gates reject before side effects. */
 for(unsigned variant=0;variant<16;variant++){
  enum kc_status s;init(&c,&f);p=plan();
  switch(variant){
   case 0:p.address=0x11;break;case 1:p.sample_rate=8000;break;
   case 2:p.count=KC_MAX_STEPS+1;break;case 3:p.read_count=KC_MAX_READ_RULES+1;break;
   case 4:p.reviews=0;break;case 5:p.steps[0].evidence=KC_REFERENCE_ONLY;break;
   case 6:p.reads[0].evidence=KC_REFERENCE_ONLY;break;case 7:p.read_count=0;break;
   case 8:p.steps[1].mask=0xff;break;case 9:p.steps[1].value=0x80;break;
   case 10:p.steps[0].source_id=0;break;case 11:p.steps[0].stage=KC_CAPTURE;break;
   case 12:p.steps[2].delay_ms=1001;break;case 13:p.mode=KC_HARDWARE;break;
   case 14:p.reads[1]=p.reads[0];p.read_count=2;break;
   case 15:c.port.mode=KC_HARDWARE;break;
  }
  id=999;s=kc_start(&c,&p,100,&id);CHECK(s==KC_INVALID || s==KC_NOT_READY);
  CHECK(f.calls==0 && id==999 && c.state==KC_OFF);
 }
 /* Expiration before every access issues no additional callback. */
 for(unsigned before=0;before<9;before++){
  init(&c,&f);p=plan();start(&c,&p);
  for(unsigned i=0;i<before;i++)CHECK(kc_poll(&c)==KC_PENDING);
  f.now=c.deadline;CHECK(kc_poll(&c)==KC_TIMEOUT);CHECK(f.calls==before);
  CHECK(kc_cleanup(&c,c.id,f.now)==KC_TIMEOUT && f.cleanup_calls==0);
  CHECK(kc_cleanup(&c,c.id,f.now+100)==KC_OK);CHECK(kc_reset_error(&c)==KC_OK);
 }
 /* Exhausted budget before a requested delay: do not call delay backend. */
 init(&c,&f);p=plan();start(&c,&p);
 for(unsigned i=0;i<4;i++)CHECK(kc_poll(&c)==KC_PENDING);
 f.now=c.deadline-1;CHECK(kc_poll(&c)==KC_TIMEOUT && f.delays==0);
 init(&c,&f);p=plan();CHECK(kc_start(&c,&p,10,&id)==KC_TIMEOUT && f.calls==0);
 c.next_id=UINT64_MAX;start(&c,&p);CHECK(kc_cancel(&c,c.id)==KC_OK);CHECK(kc_poll(&c)==KC_CANCELLED);
 CHECK(kc_cleanup(&c,c.id,200)==KC_OK);CHECK(kc_start(&c,&p,100,&id)==KC_EXHAUSTED);
 /* Cleanup late/failure/backwards acknowledgements never release ownership. */
 for(unsigned kind=0;kind<3;kind++){
  init(&c,&f);p=plan();start(&c,&p);CHECK(kc_stop(&c,c.id)==KC_PENDING);
  if(kind==0)f.cleanup_error=-110;
  if(kind==1)f.cleanup_late=true;
  if(kind==2)f.cleanup_back=true;
  CHECK(kc_cleanup(&c,c.id,20)!=KC_OK && c.state==KC_STOPPING);
  CHECK(kc_start(&c,&p,100,&id)==KC_BUSY);
 }
 printf("candidate_c_checks=%u failures=0; simulation only; hardware plan NOT_READY\n",checks);
 return 0;
}
