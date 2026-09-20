#include "i2c3_timing.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "upstream-reference.h"
int main(void){
 struct k7_i2c_timing_request r={24000000,100000,100,100,true};
 struct k7_i2c_timing out,old;unsigned pass=0,reject=0;
 memset(&old,0xa5,sizeof(old));out=old;r.inputs_known=false;
 assert(k7_i2c3_timing(&r,&out)==-EAGAIN&&!memcmp(&out,&old,sizeof(out)));
 r.inputs_known=true;r.input_hz=0;assert(k7_i2c3_timing(&r,&out)==-EINVAL);
 r.input_hz=24000000;r.bus_hz=0;assert(k7_i2c3_timing(&r,&out)==-EINVAL);
 r.bus_hz=999;assert(k7_i2c3_timing(&r,&out)==-EINVAL);
 r.bus_hz=100001;assert(k7_i2c3_timing(&r,&out)==-EINVAL);
 r.bus_hz=100000;r.input_hz=1;assert(k7_i2c3_timing(&r,&out)==-ERANGE);
 r.input_hz=UINT32_MAX;r.scl_rise_ns=UINT32_MAX;r.scl_fall_ns=UINT32_MAX;
 assert(k7_i2c3_timing(&r,&out)==-ERANGE&&!memcmp(&out,&old,sizeof(out)));
 const uint32_t clocks[]={1000000,12000000,24000000,24000001,50000000,100000000,200000000,UINT32_MAX};
 const uint32_t buses[]={1000,10000,50000,99999,100000};
 const uint32_t edges[]={0,100,300,1000};
 for(unsigned a=0;a<8;a++)for(unsigned b=0;b<5;b++)for(unsigned c=0;c<4;c++){
  r=(struct k7_i2c_timing_request){clocks[a],buses[b],edges[c],edges[c],true};out=old;
  int ret=k7_i2c3_timing(&r,&out);
  if(ret){assert(ret==-ERANGE&&!memcmp(&out,&old,sizeof(out)));reject++;}
  else{uint64_t l=(uint64_t)out.div_low+1,h=(uint64_t)out.div_high+1;
    struct i2c_timings rt={r.bus_hz,r.scl_rise_ns,r.scl_fall_ns};
    struct rk3x_i2c_calced_timings reference;
    assert(!rk3x_i2c_v1_calc_timings(r.input_hz,&rt,&reference));
    assert(reference.div_low==out.div_low&&reference.div_high==out.div_high&&reference.tuning==out.tuning);
    assert((uint64_t)r.input_hz<=(uint64_t)r.bus_hz*8*(l+h));
    assert(out.scl_hz_ceiling<=r.bus_hz && !(out.tuning&~0xff00u));
    assert(out.clkdiv==((uint32_t)out.div_high<<16|out.div_low));pass++;
  }
 }
 r=(struct k7_i2c_timing_request){24000000,100000,100,100,true};assert(!k7_i2c3_timing(&r,&out));
 printf("SYNTHETIC 24MHz input example div_low=%u div_high=%u tuning=%08x scl_ceiling=%u\n",out.div_low,out.div_high,out.tuning,out.scl_hz_ceiling);
 printf("PASS 7 explicit boundaries + 160 grid cases (%u accepted/%u rejected), all accepted match frozen upstream; no target clock read\n",pass,reject);
 return 0;
}
