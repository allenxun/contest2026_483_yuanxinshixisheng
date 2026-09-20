#define main base_regression_main
#include "test_base.c"
#undef main
struct request_sim {struct sim s;unsigned dw,dr,fail_dr,fail_dw,sticky,fail_stop_read,fail_rx,mask_writes;};
static int rr(void*x,uint32_t o,uint32_t*v){
 struct request_sim*q=x;
 if(o==0x24 && ++q->dr==q->fail_dr)return -1;
 if(o==0x10 && q->s.off && q->fail_stop_read){q->fail_stop_read=0;return -1;}
 if(o==0x34 && q->fail_rx)return -1;
 return rd(&q->s,o,v);
}
static int ww(void*x,uint32_t o,uint32_t v){
 struct request_sim*q=x;
 assert(o<0x80); /* only SAI-local register offsets */
 if(o>=0x3c && o<=0x58){q->mask_writes++;assert(0);}
 if(o==0x24){
  q->dw++;assert(!(v&0x100u));assert((v&0x1f0000u)==0x70000u);
  if(q->sticky && !(v&0x1000000u))return 0;
  if(q->dw==q->fail_dw){q->s.reg[o/4]=v;return -1;}
 }
 if(o==0x10 && (v&8))assert(q->s.reg[0x24/4]&0x1000000u);
 if(o==0x10 && q->s.off)assert(!(q->s.reg[0x24/4]&0x1000000u));
 return wr(&q->s,o,v);
}
static void setup(struct request_sim*q){memset(q,0,sizeof *q);q->s.reg[0x24/4]=0x70000u;}
int main(void){
 struct request_sim q;struct pio_result out;struct pio_rx_request_report report;uint32_t data[64];
 struct pio_port p={&q,rr,ww,tm,arm,on,off,1u<<27};
 assert(!base_regression_main());
 setup(&q);assert(!pio_run_rx_request(&p,1,4096000,data,64,32,&out,&report));
 assert(!out.held && out.frames==32 && out.rx_trace.count==32);
 assert(report.initial_dmacr==0x70000u && report.enabled_dmacr==0x1070000u && report.final_dmacr==0x70000u);
 assert(out.rx_trace.init[4]==0x1070000u && !report.disable_rc && q.dw==2);
 for(unsigned i=0;i<8;i++)assert(!report.mask_rc[i]);
 for(unsigned n=1;n<=2;n++){
  setup(&q);q.fail_dw=n;assert(pio_run_rx_request(&p,1,4096000,data,64,32,&out,&report)<0);
  assert(!(q.s.reg[9]&0x1000000u));if(n==2)assert(out.held);
 }
 for(unsigned n=1;n<=6;n++){
  setup(&q);q.fail_dr=n;int e=pio_run_rx_request(&p,1,4096000,data,64,32,&out,&report);
  if(n==4){assert(!e && out.rx_trace.init_rc[4]);}
  else assert(e<0);
  if(n>=5)assert(out.held);
 }
 setup(&q);q.sticky=1;assert(pio_run_rx_request(&p,1,4096000,data,64,32,&out,&report)<0);
 assert(out.held && report.disable_rc && (report.final_dmacr&0x1000000u));
 setup(&q);q.fail_stop_read=1;assert(pio_run_rx_request(&p,1,4096000,data,64,32,&out,&report)<0);
 assert(out.held && report.disable_attempted && !(q.s.reg[9]&0x1000000u));
 setup(&q);q.fail_rx=1;assert(pio_run_rx_request(&p,1,4096000,data,64,32,&out,&report)<0);
 assert(!out.held && !report.disable_rc && !(q.s.reg[9]&0x1000000u));
 setup(&q);q.s.mode=2;assert(pio_run_rx_request(&p,1,4096000,data,64,32,&out,&report)<0);
 assert(!out.held && !report.disable_rc);
 setup(&q);q.s.reg[9]|=0x1000000u;assert(pio_run_rx_request(&p,1,4096000,data,64,32,&out,&report)==-16);assert(!q.dw);
 setup(&q);q.s.reg[9]|=0x100u;assert(pio_run_rx_request(&p,1,4096000,data,64,32,&out,&report)==-16);assert(!q.dw);
 setup(&q);assert(pio_run_rx_request(&p,1,4096000,data,1,32,&out,&report)==-22);assert(!q.dw);
 puts("PASS request: original regression, RDE sequence/RDL unchanged, masks read-only, failures/readback/stuck cleanup held, no DMA engine; MOCK ONLY");return 0;
}
