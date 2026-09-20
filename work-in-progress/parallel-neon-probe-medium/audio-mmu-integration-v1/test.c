#include "command_core.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned reads,snaps;static int badcpu,changed,fail;
static int cpu(void*c){(void)c;return badcpu?4:0;}
static int snap(void*c,struct mp_snapshot*s)
{(void)c;memset(s,0,sizeof(*s));s->el=4;s->sctlr=1;
 s->tcr=(UINT64_C(5)<<32)|16;s->ttbr0=0x40414000;
 if(changed&&snaps)s->mair=255;
 snaps++;return 0;}
static int fetch(void*c,uint64_t pa,uint64_t*v)
{(void)c;reads++;if(fail)return -1;
 if(pa==0x40414000)*v=0x40400003;
 else if(pa==0x40400000)*v=0x40401003;
 else {assert(pa==0x40401000+((MP_TARGET>>21)&511)*8);*v=(MP_TARGET&~UINT64_C(0x1fffff))|0x401;}
 return 0;}
int main(void)
{
 struct mi_args a;struct mi_result r;struct mi_ops o={NULL,cpu,snap,fetch};unsigned i;
 const char*bad[]={"","0","0x","40400000","-0x40400000"," 0x40400000","0x40400000 ","0x100000000","0xgggg","0x40400001","0x2a610000","0x481ff000"};
 for(i=0;i<sizeof(bad)/sizeof(bad[0]);i++)assert(mi_parse(bad[i],"0x40414000",&a)!=0);
 assert(mi_parse(NULL,"0x40414000",&a)!=0);
 assert(mi_parse("0x40400000","0x40401000",&a)!=0);
 assert(mi_parse("0x40400000","0x40414000",&a)==0);
 assert(mi_allowed(&a,0x40400000)&&mi_allowed(&a,0x40414ff8));
 assert(!mi_allowed(&a,0x40415000)&&!mi_allowed(&a,0x40400001)&&!mi_allowed(&a,0x2a610034));
 assert(mi_execute(&a,&o,&r)==0&&reads==3&&r.walk.identity&&r.walk.device_ngnrne&&snaps==2);
 reads=snaps=0;changed=1;assert(mi_execute(&a,&o,&r)==MP_UNSTABLE&&reads==3);changed=0;
 reads=snaps=0;badcpu=1;assert(mi_execute(&a,&o,&r)==MP_UNSTABLE&&reads==0&&snaps==0);badcpu=0;
 reads=snaps=0;fail=1;assert(mi_execute(&a,&o,&r)==MP_READ&&reads==1);fail=0;
 assert(mi_parse("0x40400000","0x40415000",&a)==0);
 reads=snaps=0;assert(mi_execute(&a,&o,&r)==MP_RANGE&&reads==0);
 puts("PASS strict two-range args; fixed sizes/alignment/flat-RAM/overlap; no MMIO callback");
 puts("PASS CPU0; two snapshots; TTBR binding; guarded walk; changed snapshot/read failure/wrong CPU rejection");
 return 0;
}
