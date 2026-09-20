/* Procedures derived from frozen official i2c-rk3x.c; no auto-stop mode. */
#include "rk3x_registers.h"
#include <errno.h>
#define BIT(n) (UINT32_C(1)<<(n))
static uint32_t rd(struct ka_rk3x*r,unsigned off){return r->read32(r->ctx,KA_I2C3_BASE+off);}
static void wr(struct ka_rk3x*r,unsigned off,uint32_t v){r->write32(r->ctx,KA_I2C3_BASE+off,v);}
int ka_rk_begin(void *ctx,bool reading,uint8_t address,uint8_t reg,uint8_t value)
{
 struct ka_rk3x*r=ctx;uint32_t con;
 if(!r || !r->ready || !r->read32 || !r->write32 || !r->lines_idle)return -ENODEV;
 if(r->active || address!=KA_CODEC_ADDRESS)return -EBUSY;
 con=rd(r,0);
 if((con&BIT(0)) || rd(r,0x18) || r->lines_idle(r->ctx)!=1)return -EBUSY;
 r->tuning=con&0xff00u;r->active=true;r->reading=reading;r->stopping=false;
 wr(r,0x1c,0xff); /* W1C pending bits, exact upstream REG_INT_ALL. */
 if(((con>>16)&0x1ff)>=5)wr(r,0x228,0); /* Disable version5 auto-stop. */
 if(reading){
   wr(r,8,BIT(24)|((uint32_t)address<<1));wr(r,12,BIT(24)|reg);
   con=r->tuning|BIT(0)|BIT(1)|BIT(3)|BIT(6);
   wr(r,0,con);wr(r,0,con|BIT(5));wr(r,0x14,1);
 }else{
   wr(r,0x100,((uint32_t)address<<1)|((uint32_t)reg<<8)|((uint32_t)value<<16));
   wr(r,0,r->tuning|BIT(0)|BIT(3)|BIT(6));wr(r,0x10,3);
 }
 return 0;
}
int ka_rk_poll(void *ctx,size_t *tx,size_t *rx,uint8_t *value)
{
 struct ka_rk3x*r=ctx;uint32_t ipd,done;
 if(!r || !r->active || r->stopping)return -ENODEV;
 ipd=rd(r,0x1c);if(ipd&BIT(6))return -ENXIO;
 done=r->reading?BIT(3):BIT(2);
 if(!(ipd&done))return 0;
 if(r->reading){*value=(uint8_t)rd(r,0x200);*tx=1;*rx=1;}else{*tx=2;*rx=0;}
 wr(r,0x1c,done|BIT(4));return 1;
}
int ka_rk_stop(void *ctx)
{
 struct ka_rk3x*r=ctx;
 if(!r || !r->ready)return -ENODEV;
 if(!r->active)return 0; /* Never STOP an unrelated controller owner. */
 if(!r->stopping){
   wr(r,0x1c,0xff);wr(r,0,(rd(r,0)|BIT(4))&~BIT(3));r->stopping=true;
 }
 return 0;
}
int ka_rk_idle(void *ctx)
{
 struct ka_rk3x*r=ctx;
 if(!r || !r->ready)return -ENODEV;
 if(!r->active)return 1;
 if(!r->stopping)return 0;
 if(!(rd(r,0x1c)&BIT(5)))return 0;
 wr(r,0x1c,BIT(5));wr(r,0,r->tuning); /* Disable only after STOP acknowledged. */
 /* If pins remain low, retain ownership. Later cleanup retries a STOP. */
 if(r->lines_idle(r->ctx)!=1){r->stopping=false;return 0;}
 r->active=false;r->stopping=false;return 1;
}
