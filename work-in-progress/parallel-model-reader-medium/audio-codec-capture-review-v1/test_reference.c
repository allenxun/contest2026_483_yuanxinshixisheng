#include "capture_reference.h"
#include <assert.h>
#include <stdio.h>
static unsigned calls;
static uint64_t now(void *v){(void)v;++calls;return 1;}
static struct kc_io_result wr(void*v,uint8_t a,const uint8_t*b,size_t n,uint64_t d)
{(void)v;(void)a;(void)b;(void)n;(void)d;++calls;return (struct kc_io_result){0,2,0};}
static struct kc_io_result rd(void*v,uint8_t a,uint8_t b,uint8_t*c,uint64_t d)
{(void)v;(void)a;(void)b;(void)c;(void)d;++calls;return (struct kc_io_result){0,1,1};}
static int delay(void*v,uint32_t n,uint64_t d){(void)v;(void)n;(void)d;++calls;return 0;}
static int clock_ready(void*v,uint32_t a,uint32_t b,uint32_t c,uint64_t d)
{(void)v;(void)a;(void)b;(void)c;(void)d;++calls;return 0;}
static int control(void*v,enum kc_control c,uint64_t i,uint64_t d)
{(void)v;(void)c;(void)i;(void)d;++calls;return 0;}
int main(void){
 struct kc_plan p;struct kc_context c;uint64_t id=123;
 struct kc_port port={NULL,now,wr,rd,delay,clock_ready,control,KC_HARDWARE};
 k7_capture16_reference(&p);assert(p.reviews==0 && p.read_count==0 && p.count==15);
 for(size_t i=0;i<p.count;i++)assert(p.steps[i].evidence==KC_REFERENCE_ONLY);
 assert(p.steps[6].reg==0x0a && p.steps[6].value==0xf0);
 assert(p.steps[7].reg==0x0b && p.steps[7].value==0x82);
 assert(p.steps[9].reg==0x0c && p.steps[9].value==0x0c);
 assert((p.steps[9].value&0xc0)==0); /* distinct L/R ADC data, not 0x40 duplicate */
 assert(kc_init(&c,&port)==KC_OK);
 assert(kc_start(&c,&p,100,&id)==KC_NOT_READY);
 assert(calls==0 && id==123 && c.state==KC_OFF && c.next_id==1);
 puts("PASS reference plan rejected KC_NOT_READY; zero callbacks; owner/id unchanged; LIN2/RIN2 and S16 fields checked. No hardware execution.");
 return 0;
}
