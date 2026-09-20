#include "mmu_probe.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static uint64_t pages[4][512];static unsigned reads;static int fail;
static int fetch(void*c,uint64_t pa,uint64_t*v)
{(void)c;assert(pa>=0x40400000&&pa<0x40404000&&!(pa&7));reads++;
 if(fail)return -1;
 *v=pages[(pa-0x40400000)/4096][(pa%4096)/8];return 0;}
static struct mp_range ranges[]={{0x40400000,0x40404000}};
static struct mp_reader reader={NULL,fetch,ranges,1,1};
static struct mp_snapshot s;
static struct mp_report o;
static void init(void)
{memset(pages,0,sizeof(pages));memset(&s,0,sizeof(s));reads=0;fail=0;
 s.el=4;s.sctlr=1;s.tcr=(UINT64_C(5)<<32)|16;s.ttbr0=0x40400000;
 s.mair=UINT64_C(0xff00);reader.current_build_identity_proven=1;
 pages[0][0]=0x40401003;pages[1][0]=0x40402003;
 pages[2][(MP_TARGET>>21)&511]=0x40403003;
 pages[3][(MP_TARGET>>12)&511]=MP_TARGET|0x403;}
int main(void)
{
 init();assert(mp_walk(&s,&reader,&o)==0&&o.steps==4&&o.identity&&o.device_ngnrne&&o.access_flag&&reads==4);
 puts("PASS 4-level 4KiB EL1 identity Device-nGnRnE");
 init();pages[3][(MP_TARGET>>12)&511]|=4;assert(mp_walk(&s,&reader,&o)==0&&!o.device&&o.mair_byte==255);
 init();pages[2][(MP_TARGET>>21)&511]=(MP_TARGET&~UINT64_C(0x1fffff))|0x401;
 assert(mp_walk(&s,&reader,&o)==0&&o.steps==3&&o.identity);
 init();pages[1][0]=0x401;assert(mp_walk(&s,&reader,&o)==0&&o.steps==2&&o.identity);
 init();pages[3][(MP_TARGET>>12)&511]=0x12345403;assert(mp_walk(&s,&reader,&o)==0&&!o.identity);
 init();pages[3][(MP_TARGET>>12)&511]&=~UINT64_C(0x400);assert(mp_walk(&s,&reader,&o)==0&&!o.access_flag);
 init();pages[0][0]=0;assert(mp_walk(&s,&reader,&o)==MP_DESCRIPTOR&&reads==1);
 init();pages[0][0]=0x50000003;assert(mp_walk(&s,&reader,&o)==MP_RANGE&&reads==1);
 init();s.ttbr0=0x2a610000;assert(mp_walk(&s,&reader,&o)==MP_RANGE&&reads==0);
 init();s.ttbr0=0x40404000;assert(mp_walk(&s,&reader,&o)==MP_RANGE&&reads==0);
 init();reader.current_build_identity_proven=0;assert(mp_walk(&s,&reader,&o)==MP_UNSUPPORTED&&reads==0);
 init();s.el=8;assert(mp_walk(&s,&reader,&o)==MP_UNSUPPORTED&&reads==0);
 init();s.sctlr=0;assert(mp_walk(&s,&reader,&o)==MP_UNSUPPORTED&&reads==0);
 init();s.tcr|=UINT64_C(1)<<14;assert(mp_walk(&s,&reader,&o)==MP_UNSUPPORTED&&reads==0);
 init();s.tcr|=UINT64_C(1)<<7;assert(mp_walk(&s,&reader,&o)==MP_UNSUPPORTED&&reads==0);
 init();s.tcr|=UINT64_C(1)<<59;assert(mp_walk(&s,&reader,&o)==MP_UNSUPPORTED&&reads==0);
 init();s.sctlr|=UINT64_C(1)<<25;assert(mp_walk(&s,&reader,&o)==MP_UNSUPPORTED&&reads==0);
 init();pages[0][0]|=UINT64_C(1)<<48;assert(mp_walk(&s,&reader,&o)==MP_UNSUPPORTED);
 init();ranges[0].end=UINT64_MAX;assert(mp_walk(&s,&reader,&o)==MP_RANGE&&reads==0);ranges[0].end=0x40404000;
 init();s.mpidr_after=1;assert(mp_walk(&s,&reader,&o)==MP_UNSTABLE&&reads==0);
 init();fail=1;assert(mp_walk(&s,&reader,&o)==MP_READ&&reads==1);
 init();pages[2][(MP_TARGET>>21)&511]=0x2a601401;assert(mp_walk(&s,&reader,&o)==MP_DESCRIPTOR);
 assert(mp_snapshot_arm64(&s)==MP_UNSUPPORTED);
 puts("PASS Normal/wrong-PA/AF0 report; block decode; invalid/out-of-range/unknown-identity/EL/TG/MMU/migration/read-error/misaligned-block refusal");
 puts("ARM64 MRS glue not executed or cross-compiled; no physical RAM dereference provided.");
 return 0;
}
