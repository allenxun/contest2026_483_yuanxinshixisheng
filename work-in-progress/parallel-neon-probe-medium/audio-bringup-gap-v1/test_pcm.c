#include "pcm_observer.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
int main(void) {
 struct po_stats s,before,whole;po_init(&s);
 unsigned char p[]={0,128,255,127,0,0,255,255,1,0,0,1};
 assert(!po_push(&s,p,sizeof(p))&&s.frames==3);
 assert(s.channel[0].sum==-32767&&s.channel[0].sum_squares==1073741825ULL);
 assert(s.channel[0].peak==32768&&s.channel[0].clipped==1&&s.channel[0].min==-32768&&s.channel[0].max==1);
 assert(s.channel[1].sum==33022&&s.channel[1].peak==32767&&s.channel[1].clipped==1);
 assert(s.channel[1].sum_squares==1073741826ULL&&s.channel[1].nonzero==3);
 before=s;assert(po_push(&s,p,3)==EINVAL&&!memcmp(&s,&before,sizeof(s)));
 assert(po_push(&s,p,4097)==EINVAL&&!memcmp(&s,&before,sizeof(s)));
 assert(po_push(&s,NULL,4)==EINVAL&&!memcmp(&s,&before,sizeof(s)));
 assert(!po_complete(&s,3)&&po_complete(&s,4)==EIO&&po_complete(&s,0)==EINVAL);
 whole=s;po_init(&s);for(unsigned i=0;i<3;i++)assert(!po_push(&s,p+4*i,4));
 assert(!memcmp(&s,&whole,sizeof(s)));
 unsigned char zeros[4096]={0};po_init(&s);
 for(unsigned i=0;i<46;i++)assert(!po_push(&s,zeros,sizeof(zeros)));
 assert(!po_push(&s,zeros,896*4)&&!po_complete(&s,48000));
 before=s;assert(po_push(&s,p,4)==EOVERFLOW&&!memcmp(&s,&before,sizeof(s)));
 assert(s.channel[0].sum_squares==0&&s.channel[1].nonzero==0);
 printf("PASS PCM16LE stereo: signs/extrema/energy/clips/chunks/errors/48000-frame limit; bytes=%u no audio device\n",(unsigned)sizeof(s));
}
