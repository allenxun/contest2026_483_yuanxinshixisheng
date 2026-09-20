#include "rk3x_registers.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
struct model{uint32_t regs[0x22c/4];unsigned writes;bool high;};
static uint32_t rd(void*p,uintptr_t addr){struct model*m=p;assert(addr>=KA_I2C3_BASE && addr<KA_I2C3_BASE+0x22c);return m->regs[(addr-KA_I2C3_BASE)/4];}
static void wr(void*p,uintptr_t addr,uint32_t value){struct model*m=p;unsigned off=(unsigned)(addr-KA_I2C3_BASE);assert(off<0x22c);m->writes++;if(off==0x1c)m->regs[off/4]&=~value;else m->regs[off/4]=value;}
static int idle(void*p){return ((struct model*)p)->high;}
int main(void){
 struct model m={0};struct ka_rk3x r={&m,rd,wr,idle,false,false,false,false,0};size_t tx=0,rx=0;uint8_t v=0;
 assert(ka_rk_begin(&r,false,0x10,1,0x80)==-ENODEV&&!m.writes);
 r.ready=true;m.high=true;m.regs[0]=(5u<<16)|0x300;
 assert(!ka_rk_begin(&r,false,0x10,1,0x80));assert(m.regs[0x100/4]==0x800120&&m.regs[0x10/4]==3&&m.regs[0x228/4]==0);
 assert(!ka_rk_poll(&r,&tx,&rx,&v));m.regs[0x1c/4]=4;assert(ka_rk_poll(&r,&tx,&rx,&v)==1&&tx==2&&!rx);
 assert(!ka_rk_stop(&r));assert(!ka_rk_idle(&r));m.regs[0x1c/4]=32;assert(ka_rk_idle(&r)==1&&!r.active&&m.regs[0]==0x300);
 assert(!ka_rk_begin(&r,true,0x10,0x12,0));assert(m.regs[2]==0x1000020&&m.regs[3]==0x1000012&&m.regs[0x14/4]==1);
 m.regs[0x200/4]=0xab;m.regs[0x1c/4]=8;assert(ka_rk_poll(&r,&tx,&rx,&v)==1&&tx==1&&rx==1&&v==0xab);
 assert(!ka_rk_stop(&r));m.regs[0x1c/4]=32;m.high=false;assert(!ka_rk_idle(&r)&&r.active);m.high=true;
 assert(!ka_rk_stop(&r));m.regs[0x1c/4]=32;assert(ka_rk_idle(&r)==1);
 assert(!ka_rk_begin(&r,true,0x10,0,0));m.regs[0x1c/4]=8|64;assert(ka_rk_poll(&r,&tx,&rx,&v)==-ENXIO);
 puts("PASS register model: TX/RX/NAK/STOP/line hold/version5; no MMIO device");return 0;
}
