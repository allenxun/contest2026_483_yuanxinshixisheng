#include <assert.h>
#include <stdio.h>
#include "../../app/k7sound/pio.c"
struct fake { uint32_t regs[512]; unsigned writes,words,checks,off,samples; uint64_t time; int immediate,fail_off,rx,negative; };
static int read_reg(void *arg,uint32_t offset,uint32_t *value)
{
  struct fake *f=arg;
  if(offset==SAI_VERSION)*value=SAI_VER_2307;
  else if(offset==SAI_STATUS)*value=14;
  else if(offset==SAI_CLR)*value=0;
  else if(offset==SAI_TXFIFOLR)*value=f->words;
  else if(offset==SAI_RXFIFOLR && f->rx)*value=(f->regs[SAI_XFER/4]&SAI_XFER_RXS_MASK)?
    (1u<<SAI_FIFOLR_XFL0_SHIFT)|(1u<<SAI_FIFOLR_XFL1_SHIFT)|(1u<<SAI_FIFOLR_XFL2_SHIFT)|(1u<<SAI_FIFOLR_XFL3_SHIFT):0;
  else if(offset==SAI_RXDR && f->rx)*value=0x10000;
  else *value=f->regs[offset/4];
  return 0;
}
static int write_reg(void *arg,uint32_t offset,uint32_t value)
{
  struct fake *f=arg;f->writes++;
  if(offset==SAI_TXDR)f->words++;
  else f->regs[offset/4]=value;
  return 0;
}
static uint64_t time_us(void *arg){return ++((struct fake *)arg)->time;}
static int hook(void *arg){(void)arg;return 0;}
static int off(void *arg){struct fake *f=arg;f->off++;return f->fail_off?-5:0;}
static int cancelled(void *arg){struct fake *f=arg;return f->immediate || ++f->checks>=2;}
static int endpoint(void *arg,uint32_t left,uint32_t right)
{struct fake *f=arg;assert(left==0x10000 && right==0x10000);return ++f->samples==320?(f->negative?-ECANCELED:1):0;}
int main(void)
{
  int16_t pcm[320]={0};struct pio_result result;
  for(int test=0;test<3;test++)
    {
      struct fake f={0};f.immediate=test==0;f.fail_off=test==2;
      struct pio_port port={&f,read_reg,write_reg,time_us,hook,hook,off,1,cancelled,&f};
      int rc=pio_play_mono16(&port,1,4096000,pcm,320,320,&result);
      assert(rc==-ECANCELED);
      if(test==0){assert(f.writes==0 && f.off==0);}
      else
        {
          assert(f.off==1 && result.stop_result==0);
          assert((f.regs[SAI_XFER/4]&15)==0);
          assert(f.words==16); /* No additional samples after cancellation. */
          assert(result.held==(test==2));
          assert(result.amp_off_result==(test==2?-5:0));
        }
    }
  for(int test=0;test<3;test++)
    {
      struct fake f={0};f.rx=1;f.negative=test==1;f.fail_off=test==2;
      struct pio_port port={&f,read_reg,write_reg,time_us,hook,hook,off,1,NULL,NULL};
      uint32_t capture[1280];
      int rc=pio_run_grouped_sink(&port,1,4096000,capture,1280,640,&result,endpoint,&f);
      assert(rc==(test==1?-ECANCELED:test==2?-5:0));
      assert(f.samples==320 && result.frames==(test==1?319u:320u));
      assert(f.off==1 && result.stop_result==0 && result.held==(test==2));
      assert((f.regs[SAI_XFER/4]&15)==0);
    }
  puts("PIO cancellation/cleanup and successful early capture: PASS (6 cases)");
  return 0;
}
