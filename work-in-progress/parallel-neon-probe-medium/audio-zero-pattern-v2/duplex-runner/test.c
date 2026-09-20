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
 else if(o==0x20)*v=fifo(s->rh,s->rt);
 else if(o==0x6c)*v=s->stop_stuck?0:((s->regs[4]&4?0:4)|(s->regs[4]&8?0:8)|(s->regs[4]&2?0:2));
 else if(o==0x34){assert(s->rh<s->rt);*v=s->rx[s->rh++];}
 else *v=s->regs[o/4];
 return 0;
}
static int writereg(void*c,uint32_t o,uint32_t v)
{
 struct mock*s=c;s->writes++;
 if(o==0x38&&++s->paths==2&&s->restore_fail)return -1;
 if(o==0x38&&s->path_corrupt&&s->paths==1)v^=1;
 if(o==0x10&&(v&15)==15&&s->start_write_fail)return -1;
 if(o==0x30){assert(s->tt<1024);s->tx[s->tt++]=v;return 0;}
 if(o==0x14){assert((s->regs[4]&3)==3);if(!s->clear_stuck){s->th=s->tt;s->rh=s->rt;v=0;}}
 if(o==0x10&&(v&12)==12&&(s->regs[4]&12)!=12)s->last=s->now;
 if(o==0x10&&(v&12)==0&&(s->regs[4]&12)==12&&s->stop_after_start)s->stop_stuck=1;
 s->regs[o/4]=v;return 0;
}
static uint64_t timeus(void*c)
{
 struct mock*s=c;unsigned i;uint32_t w;s->now++;
 if((s->regs[4]&15)==15&&!s->stall&&s->now-s->last>=63){
  s->last=s->now;
  for(i=0;i<2;i++){
   if(s->th==s->tt){s->regs[0x2c/4]|=2;break;}
   w=s->tx[s->th++];if(s->sparse&&((s->rt/2)%4))w=0;
   assert(s->rt<1024);s->rx[s->rt++]=w;
  }
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
 unsigned i;
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
 return 0;
}
