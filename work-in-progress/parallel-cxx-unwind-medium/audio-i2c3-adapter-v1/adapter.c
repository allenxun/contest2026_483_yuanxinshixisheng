#include "adapter.h"
#include <errno.h>
#include <string.h>

enum kc_status ka_init(struct ka_adapter *a,const struct ka_backend *b,enum kc_mode mode)
{
  if (!a || !b || !b->now_ms || !b->trylock || !b->unlock || !b->begin ||
      !b->poll || !b->stop || !b->idle) return KC_INVALID;
  if (a->initialized) return KC_BUSY;
  /* Missing reviewed board I2C3 clock/timing/ownership cannot be bypassed
   * by caller review flags. This version is simulation-only. */
  if (mode!=KC_SIMULATION) return KC_NOT_READY;
  memset(a,0,sizeof(*a)); a->backend=*b; a->initialized=true;
  a->last_time=b->now_ms(b->ctx); return KC_OK;
}
static int timely(struct ka_adapter *a,uint64_t end)
{
  uint64_t now=a->backend.now_ms(a->backend.ctx);
  if (now<a->last_time) return -EIO;
  a->last_time=now;
  return now>=end ? -ETIMEDOUT : 0;
}
int ka_cleanup(struct ka_adapter *a,uint64_t end)
{
  unsigned i; int ret;
  if (!a || !a->initialized) return -ENODEV;
  if (!a->leased) return 0;
  ret=timely(a,end); if (ret) return ret;
  ret=a->backend.stop(a->backend.ctx); if (ret) return ret;
  for (i=0;i<KA_POLL_LIMIT;i++) {
    ret=timely(a,end); if (ret) return ret;
    ret=a->backend.idle(a->backend.ctx);
    if (ret<0) return ret;
    if (ret==1) {
      a->backend.unlock(a->backend.ctx); a->leased=false; return 0;
    }
  }
  return -ETIMEDOUT;
}
static struct kc_io_result transaction(struct ka_adapter *a,bool read,
    uint8_t address,uint8_t reg,uint8_t value,uint8_t *out,uint64_t end)
{
  struct kc_io_result r={-ENODEV,0,0};
  unsigned i; int ret,cleanup; uint8_t received=0; bool done=false;
  if (!a || !a->initialized) return r;
  if (address!=KA_CODEC_ADDRESS || (read && !out)) {r.error=-EINVAL;return r;}
  if (a->leased || a->poisoned) {r.error=-EBUSY;return r;}
  ret=timely(a,end); if (ret) {r.error=ret;return r;}
  ret=a->backend.trylock(a->backend.ctx); if (ret) {r.error=ret;return r;}
  a->leased=true;
  ret=timely(a,end);
  if (!ret) ret=a->backend.begin(a->backend.ctx,read,address,reg,value);
  if (!ret) {
    for (i=0;i<KA_POLL_LIMIT;i++) {
      ret=timely(a,end); if (ret) break;
      ret=a->backend.poll(a->backend.ctx,&r.tx_done,&r.rx_done,&received);
      if (ret<0) break;
      if (ret==1) {done=true;ret=0;break;}
    }
    if (!done && ret==0) ret=-ETIMEDOUT;
  }
  if (!ret && (r.tx_done!=(read?1u:2u) || r.rx_done!=(read?1u:0u))) ret=-EIO;
  if (ret) a->poisoned=true;
  cleanup=ka_cleanup(a,end);
  if (cleanup) {a->poisoned=true;if (!ret) ret=cleanup;}
  /* Report a late callback result as failure too. No asynchronous buffer use. */
  if (!ret) ret=timely(a,end);
  if (ret) a->poisoned=true;
  if (!ret && read) *out=received;
  r.error=ret; return r;
}
struct kc_io_result ka_write(void *ctx,uint8_t address,const uint8_t *bytes,size_t n,uint64_t end)
{
  struct kc_io_result invalid={-EINVAL,0,0};
  if (!bytes || n!=2) return invalid;
  return transaction(ctx,false,address,bytes[0],bytes[1],NULL,end);
}
struct kc_io_result ka_read(void *ctx,uint8_t address,uint8_t reg,uint8_t *value,uint64_t end)
{
  return transaction(ctx,true,address,reg,0,value,end);
}
