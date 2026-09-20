#include "duplex.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct mock {
 uint32_t regs[128],tx[1024],rx[1024];
 unsigned th,tt,rh,rt,paths,ampcalls,reads,writes;
 uint64_t now,last;
 int sparse,stall,clear_stuck,stop_stuck,restore_fail,read_fail,amp_fail;
 int stop_after_start,start_write_fail,path_corrupt;
 int rx_writes,rx_restore_fail,rx_corrupt_active;
 int guard_hw,ready_stall,unknown_bank,bad_depth;
 int path1_corrupt,path1_restore_corrupt;
 unsigned gh[2],gt[2],greads,saw_one_each,first_read_raw;
 uint32_t gb[2][512];
};
static struct mock m;
static struct dl_result r;
static uint32_t capture[512];
static unsigned fifo(unsigned a,unsigned b)
{unsigned i,n[4]={0};for(i=a;i<b;i++)n[(i/2)%4]++;return n[0]|n[1]<<6|n[2]<<12|n[3]<<18;}
static int readreg(void*c,uint32_t o,uint32_t*v)
{
 struct mock*s=c;s->reads++;
 if(o==0x34&&s->read_fail){s->read_fail=0;return -1;}
 if(o==0x1c)*v=fifo(s->th,s->tt);
 else if(o==0x20&&s->guard_hw){
  *v=(s->gt[0]-s->gh[0])|((s->gt[1]-s->gh[1])<<6);
  if(*v==0x41)s->saw_one_each++;
  if((s->regs[4]&15)==15){if(s->unknown_bank)*v|=0x1000;if(s->bad_depth)*v=33;}
 }
 else if(o==0x20)*v=fifo(s->rh,s->rt);
 else if(o==0x6c)*v=s->stop_stuck?0:((s->regs[4]&4?0:4)|(s->regs[4]&8?0:8)|(s->regs[4]&2?0:2));
 else if(o==0x34&&s->guard_hw){unsigned bank=(s->greads/2)%2;
  if(!s->greads)s->first_read_raw=(s->gt[0]-s->gh[0])|((s->gt[1]-s->gh[1])<<6);
  assert(s->gh[bank]<s->gt[bank]);*v=s->gb[bank][s->gh[bank]++];s->greads++;
 }
 else if(o==0x34){assert(s->rh<s->rt);*v=s->rx[s->rh++];}
 else *v=s->regs[o/4];
 return 0;
}
static int writereg(void*c,uint32_t o,uint32_t v)
{
 struct mock*s=c;s->writes++;
 if(o==0x38&&++s->paths==2&&s->restore_fail)return -1;
 if(o==0x38&&s->path_corrupt&&s->paths==1)v^=1;
 if(o==0x38&&s->path1_corrupt&&s->paths==1)v^=1u<<10;
 if(o==0x38&&s->path1_restore_corrupt&&s->paths==2)v&=~(3u<<10);
 if(o==8){s->rx_writes++;
  if(s->rx_writes==2&&s->rx_restore_fail)return -1;
  if(s->rx_writes==1&&s->rx_corrupt_active)v^=1u<<20;
 }
 if(o==0x10&&(v&15)==15&&s->start_write_fail)return -1;
 if(o==0x30){assert(s->tt<1024);s->tx[s->tt++]=v;return 0;}
 if(o==0x14){assert((s->regs[4]&3)==3);if(!s->clear_stuck){s->th=s->tt;s->rh=s->rt;s->gh[0]=s->gt[0];s->gh[1]=s->gt[1];v=0;}}
 if(o==0x10&&(v&12)==12&&(s->regs[4]&12)!=12)s->last=s->now;
 if(o==0x10&&(v&12)==0&&(s->regs[4]&12)==12&&s->stop_after_start)s->stop_stuck=1;
 s->regs[o/4]=v;return 0;
}
static uint64_t timeus(void*c)
{
 struct mock*s=c;unsigned i;uint32_t w;s->now++;
 if(s->guard_hw){
  if((s->regs[4]&15)==15&&s->now-s->last>=32&&(!s->ready_stall||!s->gt[0])){
   s->last=s->now;assert(s->th<s->tt&&s->gt[0]<512&&s->gt[1]<512);
   w=s->tx[s->th++];s->gb[0][s->gt[0]++]=w;
   s->gb[1][s->gt[1]++]=((s->regs[0x38/4]>>10)&3)?0:w;
  }
  return s->now;
 }
 if((s->regs[4]&15)==15&&!s->stall&&s->now-s->last>=63){
  s->last=s->now;
  for(i=0;i<2;i++){
   if(s->th==s->tt){s->regs[0x2c/4]|=2;break;}
   w=s->tx[s->th++];if(s->sparse&&((s->rt/2)%4))w=0;
   assert(s->rt<1024);s->rx[s->rt++]=w;
  }
  /* Deliberate model of documented 2 parallel RX lanes: lane1 allzero.
   * This is software timing coverage, not a claim about real hardware. */
  if(((s->regs[8/4]>>20)&3)==1){s->rx[s->rt++]=0;s->rx[s->rt++]=0;}
 }
 return s->now;
}
static int low(void*c){struct mock*s=c;s->ampcalls++;return s->amp_fail?-1:0;}
static struct dl_port p={&m,readreg,writereg,timeus,low};
static void init(void)
{memset(&m,0,sizeof(m));memset(capture,0xa5,sizeof(capture));m.regs[0x70/4]=0x23073576;m.regs[0x38/4]=0xe4e4;}
static int run(unsigned n){return dl_run(&p,1,1,4096000,capture,512,n,&r);}
int main(void)
{
 unsigned i,j;uint32_t w,z;
 init();assert(run(256)==0);assert(r.frames==256&&r.ntx==64&&r.nrx==64&&!r.held);
 assert(r.path_active==0x4e4e4&&r.path_restored==0xe4e4&&r.max_tx==16);
 for(i=0;i<512;i++)assert(capture[i]==m.tx[i]);
 printf("PASS full raw markers frames=%u tx_queued=%u polls=%u trace=%u/%u elapsed=%llu\n",r.frames,r.tx_words,r.polls,r.ntx,r.nrx,(unsigned long long)(r.end_us-r.start_us));
 init();m.sparse=1;assert(run(128)==0);for(i=0;i<256;i++)assert(capture[i]==((i/2)%4?0:m.tx[i]));
 puts("PASS sparse simulator zeros preserved; transfer success is NOT content acceptance");
 init();assert(run(257)==-22&&m.reads==0&&m.writes==0);
 init();assert(dl_run(&p,1,0,4096000,capture,512,128,&r)==-38&&m.writes==0);
 init();m.amp_fail=1;assert(run(128)!=0&&r.held&&m.writes==0);
 init();m.regs[0x24/4]=1u<<24;assert(run(128)==-16&&m.writes==0);
 init();m.read_fail=1;assert(run(128)!=0&&!r.held&&r.stop_rc==0&&r.path_restored==0xe4e4);
 init();m.stall=1;assert(run(128)==-110&&!r.held);
 init();m.clear_stuck=1;assert(run(128)!=0&&r.held&&r.stop_rc==-110&&m.paths==1&&(m.regs[4]&3)==3);
 init();m.restore_fail=1;assert(run(128)!=0&&r.held&&r.restore_rc==-5);
 init();m.stop_stuck=1;assert(run(128)==-16&&m.writes==0);
 init();m.stop_after_start=1;assert(run(128)!=0&&r.held&&r.stop_rc==-110&&m.paths==1);
 init();m.start_write_fail=1;assert(run(128)!=0&&!r.held&&r.stop_rc==0);
 init();m.path_corrupt=1;assert(run(128)==-71&&!r.held&&r.path_restored==0xe4e4&&r.tx_words==0);
 puts("PASS bounds/common/DMA/amp gates; RX error; deadline; stuck clear/stop; restore failure; idle refusal; start write failure; PATH readback mismatch");
 puts("No actual SAI/FIFO/codec behavior validated by this simulator.");
 init();assert(dl_run_route(&p,1,1,4096000,capture,512,128,DL_ROUTE_RX_ALL_SDI0,&r)==0);
 assert(r.path_active==0x400e4&&r.path_restored==0xe4e4&&!r.held);
 init();m.regs[0x38/4]=0xb4e4;
 assert(dl_run_route(&p,1,1,4096000,capture,512,128,DL_ROUTE_RX_ALL_SDI0,&r)==0);
 assert(r.path_active==0x400e4&&r.path_restored==0xb4e4&&(r.path_active&255)==0xe4);
 init();m.path_corrupt=1;
 assert(dl_run_route(&p,1,1,4096000,capture,512,128,DL_ROUTE_RX_ALL_SDI0,&r)==-71&&r.path_restored==0xe4e4&&!r.held);
 init();m.restore_fail=1;
 assert(dl_run_route(&p,1,1,4096000,capture,512,128,DL_ROUTE_RX_ALL_SDI0,&r)!=0&&r.held);
 init();assert(dl_run_route(&p,1,1,4096000,capture,512,256,DL_ROUTE_RX_ALL_SDI0,&r)==-22&&m.writes==0);
 init();assert(dl_run_route(&p,1,1,4096000,capture,512,128,2,&r)==-22&&m.writes==0);
 puts("PASS RX_ALL SDI0 PATH=000400e4; nonzero old RX routes restored; TX e4 unchanged; mismatch/restore errors; explicit 128-frame bound");
 for(i=0;i<288;i++){
  assert(dl_numbered_marker(i,&w)==0&&w!=0&&(w&255)==0);
  assert((((w>>8)&4095)-1)*8+((w>>20)&7)==i);
  for(j=0;j<i;j++){assert(dl_numbered_marker(j,&z)==0&&w!=z);}
 }
 assert(dl_numbered_marker(288,&w)==-22&&dl_numbered_marker(0,NULL)==-22);
 init();assert(dl_run_numbered(&p,1,1,4096000,capture,512,&r)==0);
 assert(r.frames==128&&r.path_active==0x4e4e4&&r.path_restored==0xe4e4&&!r.held);
 for(i=0;i<r.tx_words;i++){assert(dl_numbered_marker(i,&w)==0&&m.tx[i]==w);}
 for(i=0;i<256;i++){assert(dl_numbered_marker(i,&w)==0&&capture[i]==w);}
 init();m.regs[0x38/4]=0x00e4;
 assert(dl_run_numbered(&p,1,1,4096000,capture,512,&r)==-38&&m.writes==0);
 init();m.restore_fail=1;assert(dl_run_numbered(&p,1,1,4096000,capture,512,&r)!=0&&r.held);
 init();m.clear_stuck=1;assert(dl_run_numbered(&p,1,1,4096000,capture,512,&r)!=0&&r.held);
 puts("PASS all 288 markers unique/invertible; numbered raw capture; default route required; held failures preserved");
 init();assert(dl_run_numbered_rx2(&p,1,1,4096000,capture,512,&r)==0);
 assert(r.frames==128&&r.rxcr_active==0x00500fff&&r.rx_restore_rc==0&&!r.held);
 assert((r.rxcr_restored&0x300000)==0&&r.path_active==0x4e4e4);
 assert(m.regs[0]==0x00400fff&&m.regs[4/4]==0x101f03f);
 for(i=0;i<256;i++){if(i%4<2){assert(dl_numbered_marker(i/4*2+i%4,&w)==0&&capture[i]==w);}else assert(capture[i]==0);}
 printf("PASS synthetic RX2 128 pairs elapsed=%llu us raw lane1 zeros preserved\n",(unsigned long long)(r.end_us-r.start_us));
 init();m.regs[8/4]=0x00200fff;
 assert(dl_run_numbered_rx2(&p,1,1,4096000,capture,512,&r)==0&&(r.rxcr_restored&0x300000)==0x200000);
 init();m.rx_restore_fail=1;assert(dl_run_numbered_rx2(&p,1,1,4096000,capture,512,&r)!=0&&r.held&&r.rx_restore_rc==-5);
 init();m.rx_corrupt_active=1;assert(dl_run_numbered_rx2(&p,1,1,4096000,capture,512,&r)!=0&&!r.held&&r.tx_words==0);
 init();m.stop_after_start=1;assert(dl_run_numbered_rx2(&p,1,1,4096000,capture,512,&r)!=0&&r.held&&m.rx_writes==1);
 puts("PASS CSR readback, nonzero old CSR restore, restore failure held, stop failure skips restore");
 init();m.guard_hw=1;
 assert(dl_run_numbered_rx2_guard(&p,1,1,4096000,capture,512,&r)==0);
 assert(m.saw_one_each&&m.first_read_raw==0x82&&m.greads==256&&!r.held);
 assert(r.rxcr_restored==0x00400fff&&r.path_restored==0xe4e4);
 for(i=0;i<256;i++){if(i%4<2){assert(dl_numbered_marker(i/4*2+i%4,&w)==0&&capture[i]==w);}else assert(capture[i]==0);}
 puts("PASS guarded: startup bank0=1/bank1=1 waits; first RXDR at2/2; all raw words retained");
 init();m.guard_hw=m.unknown_bank=1;
 assert(dl_run_numbered_rx2_guard(&p,1,1,4096000,capture,512,&r)==-71&&!r.held&&!m.greads&&r.rx_restore_rc==0);
 init();m.guard_hw=m.bad_depth=1;
 assert(dl_run_numbered_rx2_guard(&p,1,1,4096000,capture,512,&r)==-71&&!r.held&&!m.greads);
 init();m.guard_hw=m.ready_stall=1;
 assert(dl_run_numbered_rx2_guard(&p,1,1,4096000,capture,512,&r)==-110&&!r.held&&!m.greads&&m.saw_one_each);
 init();m.guard_hw=m.unknown_bank=m.clear_stuck=1;
 assert(dl_run_numbered_rx2_guard(&p,1,1,4096000,capture,512,&r)==-71&&r.held&&r.stop_rc==-110);
 puts("PASS unknown bank/depth refusal cleanup; readiness deadline; cleanup failure held");
 init();m.guard_hw=1;
 assert(dl_run_numbered_rx2_guard_same(&p,1,1,4096000,capture,512,&r)==0);
 assert(r.path_active==0x4e0e4&&r.path_restored==0xe4e4&&!r.held);
 assert(r.rxcr_active==0x00500fff&&m.regs[0]==0x00400fff&&m.regs[4/4]==0x101f03f);
 for(i=0;i<256;i++){assert(dl_numbered_marker(i/4*2+i%2,&w)==0&&capture[i]==w);}
 init();m.guard_hw=m.path1_corrupt=1;
 assert(dl_run_numbered_rx2_guard_same(&p,1,1,4096000,capture,512,&r)==-71&&!r.held&&r.tx_words==0);
 init();m.guard_hw=m.path1_restore_corrupt=1;
 assert(dl_run_numbered_rx2_guard_same(&p,1,1,4096000,capture,512,&r)==-71&&r.held&&r.restore_rc==-71);
 init();m.guard_hw=m.restore_fail=1;
 assert(dl_run_numbered_rx2_guard_same(&p,1,1,4096000,capture,512,&r)!=0&&r.held);
 puts("PASS same-input PATH4e0e4; nonzero original path1 restored; route readback and restore-bit mismatch fail");
 return 0;
}
