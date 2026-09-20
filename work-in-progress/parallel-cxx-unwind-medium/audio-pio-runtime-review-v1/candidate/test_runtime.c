#include "pio.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#undef assert
#define assert(x) do {if(!(x)){fprintf(stderr,"failed line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
#define BIT(n) (UINT32_C(1)<<(n))
#define GENMASK(h,l) ((UINT32_MAX>>(31-(h))) & (UINT32_MAX<<(l)))
#include "input/rockchip_sai.h"
struct mock {uint32_t r[32];unsigned words,read_words,loops;int mode;uint64_t time;};
/* mode0 TX terminal underflow; mode1 TX middle underflow;
 * mode2 RX complete; mode3 RX second-word read fails. */
static int rd(void *p,uint32_t o,uint32_t *v){
 struct mock*m=p;
 if(o==SAI_RXDR&&m->mode==3&&m->read_words==1)return -1;
 *v=m->r[o/4];
 if(o==SAI_VERSION)*v=SAI_VER_2307;
 if(o==SAI_STATUS)*v=14;
 if(o==SAI_CLR)*v=0;
 if(o==SAI_INTSR && (m->r[SAI_XFER/4]&12)){
  m->loops++;
  if(m->mode<2){m->words=0;*v=SAI_INTSR_TXUI_ACT;}
 }
 if(o==SAI_TXFIFOLR)*v=m->words;
 if(o==SAI_RXFIFOLR)*v=(m->r[SAI_XFER/4]&8)?2:0;
 if(o==SAI_RXDR){
  if(m->mode==3&&m->read_words==1)return -1;
  *v=0xabc00000u+m->read_words++;
 }
 return 0;
}
static int wr(void*p,uint32_t o,uint32_t v){struct mock*m=p;m->r[o/4]=v;if(o==SAI_TXDR)m->words++;return 0;}
static uint64_t us(void*p){return ++((struct mock*)p)->time;}
static int hook(void*p){(void)p;return 0;}
int main(void){
 struct mock m;struct pio_result out;uint32_t data[6];unsigned i;int rc;
 for(int mode=0;mode<4;mode++){
  memset(&m,0,sizeof m);m.mode=mode;
  for(i=0;i<6;i++)data[i]=0xdeadbeef;
  struct pio_port p={&m,rd,wr,us,hook,hook,hook,1u<<27};
  rc=pio_run(&p,1,4096000,mode<2,data,6,mode==0?8:(mode==1?16:1),&out);
  printf("observed mode=%d rc=%d frames=%u held=%d stop=%d\n",mode,rc,out.frames,out.held,out.stop_result);
  if(mode<2){assert(rc==-75&&out.frames==8&&!out.held); assert(out.error_intsr==SAI_INTSR_TXUI_ACT && out.error_fifo_valid && out.error_fifo_raw==0); assert(out.tx_tail_candidate==(unsigned)(mode==0));}
  if(mode==2){assert(rc==0&&out.frames==1&&data[0]==0xabc00000&&data[1]==0xabc00001);}
  if(mode==3){assert(rc==-5&&!out.frames&&data[0]==0xabc00000&&data[1]==0xdeadbeef);}
  for(i=2;i<6;i++)assert(data[i]==0xdeadbeef);
  printf("synthetic mode=%d result=%d frames=%u held=%d samples=%08x,%08x\n",mode,rc,out.frames,out.held,data[0],data[1]);
 }
 puts("PASS frozen actual PIO: terminal TXUI remains rejected, middle TXUI rejected, real RX words preserved, partial pair uncounted, no zero padding");
 return 0;
}
