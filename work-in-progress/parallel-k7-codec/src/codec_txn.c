#include "codec_txn.h"
#include <string.h>
#include <limits.h>

static bool evidence_ok(enum kc_mode mode,enum kc_evidence e)
{return mode==KC_SIMULATION?e==KC_SIM_ONLY:e==KC_TARGET_REVIEWED;}
static enum kc_status validate(const struct kc_plan *p)
{
 size_t i,j;bool capture=false,init=false;
 if(!p || (p->mode!=KC_HARDWARE && p->mode!=KC_SIMULATION) ||
    p->count==0 || p->count>KC_MAX_STEPS || p->read_count>KC_MAX_READ_RULES ||
    p->address!=0x10 || p->sample_rate!=16000 || p->mclk!=4096000 ||
    p->bclk!=512000 || p->slots!=2 || p->slot_bits!=16)return KC_INVALID;
 if(p->reviews!=KC_REVIEW_ALL)return KC_NOT_READY;
 for(i=0;i<p->read_count;i++) {
  if(!p->reads[i].source_id || !p->reads[i].allowed_mask ||
     !evidence_ok(p->mode,p->reads[i].evidence))return KC_NOT_READY;
  for(j=0;j<i;j++)if(p->reads[j].reg==p->reads[i].reg)return KC_INVALID;
 }
 for(i=0;i<p->count;i++) {
  const struct kc_step *s=&p->steps[i];bool allowed=false;
  if(!s->source_id || !evidence_ok(p->mode,s->evidence))return KC_NOT_READY;
  if(s->stage==KC_CAPTURE)capture=true;
  else if(s->stage==KC_INIT && !capture)init=true;
  else return KC_INVALID;
  switch(s->kind) {
   case KC_WRITE:if(s->mask || s->delay_ms)return KC_INVALID;break;
   case KC_READ_VERIFY:
    if(!s->mask || (s->value & (uint8_t)~s->mask) || s->delay_ms)return KC_INVALID;
    for(j=0;j<p->read_count;j++)if(p->reads[j].reg==s->reg &&
       (s->mask & (uint8_t)~p->reads[j].allowed_mask)==0)allowed=true;
    if(!allowed)return KC_NOT_READY;
    break;
   case KC_DELAY:if(!s->delay_ms || s->delay_ms>1000 || s->reg || s->value || s->mask)return KC_INVALID;break;
   default:return KC_INVALID;
  }
 }
 return init && capture?KC_OK:KC_NOT_READY;
}
static enum kc_status fail(struct kc_context *c,enum kc_status status)
{c->result=status;c->failed_step=c->index;c->failed_phase=c->phase;c->state=KC_STOPPING;return status;}
static enum kc_status checkpoint(struct kc_context *c)
{
 uint64_t now=c->port.now_ms(c->port.ctx);
 if(now<c->last_time){c->clock_fault=true;return fail(c,KC_CLOCK);}
 c->last_time=now;
 if(c->cancel)return fail(c,KC_CANCELLED);
 if(now>=c->deadline)return fail(c,KC_TIMEOUT);
 return KC_OK;
}
enum kc_status kc_init(struct kc_context *c,const struct kc_port *port)
{
 if(!c || !port || !port->now_ms || !port->write || !port->read ||
    !port->delay_ms || !port->clock_ready || !port->control ||
    (port->mode!=KC_HARDWARE && port->mode!=KC_SIMULATION))return KC_INVALID;
 memset(c,0,sizeof(*c));c->port=*port;c->next_id=1;c->failed_step=SIZE_MAX;
 return KC_OK;
}
enum kc_status kc_start(struct kc_context *c,const struct kc_plan *plan,uint64_t deadline,uint64_t *id)
{
 enum kc_status s;uint64_t now;
 if(!c || !id)return KC_INVALID;
 if(c->in_call || c->state!=KC_OFF)return KC_BUSY;
 s=validate(plan);if(s!=KC_OK)return s;
 if(plan->mode!=c->port.mode)return KC_INVALID;
 if(!c->next_id)return KC_EXHAUSTED;
 c->in_call=true;now=c->port.now_ms(c->port.ctx);c->in_call=false;
 if(deadline<=now)return KC_TIMEOUT;
 c->plan=*plan; /* immutable owned snapshot */
 c->id=c->next_id;c->next_id=c->next_id==UINT64_MAX?0:c->next_id+1;
 c->deadline=deadline;c->last_time=now;c->index=0;c->failed_step=SIZE_MAX;
 c->port_error=0;c->tx_done=0;c->rx_done=0;c->cancel=false;c->clock_checked=false;c->result=KC_PENDING;
 c->cleanup_port_error=0;c->phase=KC_PHASE_NONE;c->failed_phase=KC_PHASE_NONE;
 c->cleanup_result=KC_PENDING;c->state=KC_POWERING;*id=c->id;return KC_PENDING;
}
enum kc_status kc_cancel(struct kc_context *c,uint64_t id)
{
 if(!c || !id || id!=c->id)return KC_STALE;
 if(c->state==KC_OFF || c->state==KC_ERROR)return KC_STALE;
 c->cancel=true;return KC_OK;
}
enum kc_status kc_stop(struct kc_context *c,uint64_t id)
{
 if(!c || !id || id!=c->id)return KC_STALE;
 if(c->in_call)return KC_BUSY;
 if(c->state==KC_OFF || c->state==KC_ERROR)return KC_STALE;
 if(c->state!=KC_STOPPING){c->result=KC_CANCELLED;c->state=KC_STOPPING;}
 return KC_PENDING;
}
enum kc_status kc_poll(struct kc_context *c)
{
 enum kc_status status;struct kc_io_result io={0,0,0};int ret=0;
 uint8_t value=0,bytes[2];const struct kc_step *s;uint64_t delay_begin=0;
 if(!c)return KC_INVALID;
 if(c->in_call)return KC_BUSY;
 if(c->state==KC_STOPPING)return c->result;
 if(c->state==KC_OFF || c->state==KC_ERROR)return KC_NOT_READY;
 c->in_call=true;
 c->phase=c->state==KC_POWERING?KC_PHASE_POWER:c->state==KC_READY?KC_PHASE_READY:
          !c->clock_checked?KC_PHASE_CLOCK:c->index==c->plan.count?KC_PHASE_CAPTURE:KC_PHASE_STEP;
 status=checkpoint(c);if(status!=KC_OK)goto out;
 if(c->state==KC_READY){status=KC_OK;goto out;}
 if(c->state==KC_POWERING) {
  ret=c->port.control(c->port.ctx,KC_POWER_PREPARE,c->id,c->deadline);
  c->port_error=ret;
  status=checkpoint(c);if(status!=KC_OK)goto out;
  if(ret){c->port_error=ret;status=fail(c,KC_IO);goto out;}
  c->state=KC_INITIALIZING;status=KC_PENDING;goto out;
 }
 if(!c->clock_checked) {
  ret=c->port.clock_ready(c->port.ctx,c->plan.sample_rate,c->plan.mclk,c->plan.bclk,c->deadline);
  c->port_error=ret;
  status=checkpoint(c);if(status!=KC_OK)goto out;
  if(ret){c->port_error=ret;status=fail(c,KC_CLOCK);goto out;}
  c->clock_checked=true;status=KC_PENDING;goto out;
 }
 if(c->index==c->plan.count) {
  ret=c->port.control(c->port.ctx,KC_CAPTURE_PREPARE,c->id,c->deadline);
  c->port_error=ret;
  status=checkpoint(c);if(status!=KC_OK)goto out;
  if(ret){c->port_error=ret;status=fail(c,KC_IO);goto out;}
  c->state=KC_READY;c->result=KC_OK;status=KC_OK;goto out;
 }
 s=&c->plan.steps[c->index];
 if(s->stage==KC_CAPTURE)c->state=KC_PREPARING;
 switch(s->kind) {
  case KC_WRITE:
   bytes[0]=s->reg;bytes[1]=s->value;
   io=c->port.write(c->port.ctx,c->plan.address,bytes,2,c->deadline);break;
  case KC_READ_VERIFY:
   io=c->port.read(c->port.ctx,c->plan.address,s->reg,&value,c->deadline);break;
  case KC_DELAY:
   if(s->delay_ms>c->deadline-c->last_time){status=fail(c,KC_TIMEOUT);goto out;}
   delay_begin=c->last_time;
   ret=c->port.delay_ms(c->port.ctx,s->delay_ms,c->deadline);break;
 }
 c->port_error=ret?ret:io.error;c->tx_done=io.tx_done;c->rx_done=io.rx_done;
 status=checkpoint(c);if(status!=KC_OK)goto out;
 if(ret || io.error){c->port_error=ret?ret:io.error;status=fail(c,KC_IO);goto out;}
 if((s->kind==KC_WRITE && (io.tx_done!=2 || io.rx_done!=0)) ||
    (s->kind==KC_READ_VERIFY && (io.tx_done!=1 || io.rx_done!=1)))
  {status=fail(c,KC_SHORT);goto out;}
 if(s->kind==KC_DELAY && c->last_time-delay_begin<s->delay_ms){status=fail(c,KC_DELAY_ERROR);goto out;}
 if(s->kind==KC_READ_VERIFY && (value&s->mask)!=s->value){status=fail(c,KC_READBACK);goto out;}
 ++c->index;status=KC_PENDING;
out:c->in_call=false;return status;
}
enum kc_status kc_cleanup(struct kc_context *c,uint64_t id,uint64_t deadline)
{
 uint64_t before,after;int ret;enum kc_status status;
 if(!c || !id || id!=c->id)return KC_STALE;
 if(c->in_call)return KC_BUSY;
 if(c->state!=KC_STOPPING)return KC_NOT_READY;
 c->in_call=true;before=c->port.now_ms(c->port.ctx);
 if(before<c->last_time)c->clock_fault=true;
 if(deadline<=before){status=KC_TIMEOUT;goto out;}
 ret=c->port.control(c->port.ctx,KC_QUIESCE,c->id,deadline);
 after=c->port.now_ms(c->port.ctx);
 c->cleanup_port_error=ret;
 if(ret){status=KC_IO;goto out;}
 /* Reject a late or clock-inconsistent acknowledgement conservatively. */
 if(after<before){c->clock_fault=true;status=KC_CLOCK;goto out;}
 if(after>=deadline){status=KC_TIMEOUT;goto out;}
 c->state=(c->result==KC_CANCELLED && !c->clock_fault)?KC_OFF:KC_ERROR;
 status=KC_OK;
out:c->cleanup_result=status;c->in_call=false;return status;
}
enum kc_status kc_reset_error(struct kc_context *c)
{
 if(!c)return KC_INVALID;
 if(c->in_call)return KC_BUSY;
 if(c->state!=KC_ERROR || c->clock_fault)return KC_NOT_READY;
 c->state=KC_OFF;return KC_OK;
}
void kc_es8388_reference(struct kc_plan *p)
{
 if(!p)return;
 memset(p,0,sizeof(*p));p->mode=KC_HARDWARE;p->address=0x10;
 p->sample_rate=16000;p->mclk=4096000;p->bclk=512000;p->slots=2;p->slot_bits=16;
 p->reviews=KC_REVIEW_IDENTITY;p->count=2;
 /* Official es8323.c:98-102; es8323.h:15. Reference != target validation. */
 p->steps[0]=(struct kc_step){KC_WRITE,KC_INIT,KC_REFERENCE_ONLY,1,0x00,0x80,0,0};
 p->steps[1]=(struct kc_step){KC_WRITE,KC_INIT,KC_REFERENCE_ONLY,1,0x00,0x00,0,0};
}
