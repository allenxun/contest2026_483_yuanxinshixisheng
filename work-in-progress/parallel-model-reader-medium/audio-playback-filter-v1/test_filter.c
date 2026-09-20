#include "playback_filter.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
static uint32_t src[96000],dst[96000];static unsigned checks;
#define CHECK(e) do{assert(e);checks++;}while(0)
static double sample(uint32_t w){return w<=INT32_MAX?(double)w:-1.0-(double)(UINT32_MAX-w);}
static void tone(double hz){for(unsigned i=0;i<48000;i++){int32_t v=(int32_t)(100000000.0*sin(2*3.14159265358979323846*hz*i/16000));src[2*i]=(uint32_t)v;src[2*i+1]=(uint32_t)(-v);}}
static double rms(const uint32_t*x){double s=0;for(unsigned i=1600;i<48000;i++){double v=sample(x[2*i]);s+=v*v;}return sqrt(s/46400);}
int main(void){uint32_t sat=99;double a=(double)AF_HP_Q30/1073741824.;
 CHECK(fabs(a-exp(-2*3.14159265358979323846*80/16000))<.5/1073741824.);
 memset(src,0,sizeof src);CHECK(!af_filter(src,96000,dst,96000,48000,AF_MA4,&sat));CHECK(!sat);
 for(unsigned i=0;i<96000;i++)CHECK(dst[i]==0);
 src[0]=400;src[1]=(uint32_t)-400;
 CHECK(!af_filter(src,96000,dst,96000,8,AF_MA4,&sat));
 for(unsigned i=0;i<8;i++){CHECK(dst[2*i]==(i<4?100u:0u));CHECK(dst[2*i+1]==(i<4?(uint32_t)-100:0u));}
 for(unsigned i=0;i<96000;i++)src[i]=1000000;
 CHECK(!af_filter(src,96000,dst,96000,48000,AF_MA4,&sat));CHECK(dst[0]==250000&&dst[6]==1000000&&dst[95999]==1000000);
 CHECK(!af_filter(src,96000,dst,96000,48000,AF_MA4_HP80,&sat));CHECK(dst[95998]==0&&dst[95999]==0&&!sat);
 for(unsigned i=0;i<96000;i++)src[i]=(i/200)%2?0x80000000u:0x7fffffffu;
 CHECK(!af_filter(src,96000,dst,96000,48000,AF_MA4_HP80,&sat));CHECK(sat>0);printf("extreme step saturations=%u\n",sat);
 for(unsigned f=0;f<3;f++){
  const double hz[3]={50,1000,4000};tone(hz[f]);double input=rms(src);
  for(unsigned mode=1;mode<=2;mode++){
   CHECK(!af_filter(src,96000,dst,96000,48000,(enum af_mode)mode,&sat));CHECK(!sat);
   double measured=rms(dst)/input,w=2*3.14159265358979323846*hz[f]/16000;
   double expected=fabs(sin(2*w)/(4*sin(w/2)));
   if(mode==2)expected*=a*sqrt(2-2*cos(w))/sqrt(1+a*a-2*a*cos(w));
   CHECK(fabs(measured-expected)<.00002);
   for(unsigned i=0;i<48000;i++)CHECK(sample(dst[2*i])==-sample(dst[2*i+1]));
   printf("hz=%.0f mode=%u measured=%.9f expected=%.9f\n",hz[f],mode,measured,expected);
  }
 }
 /* Deterministic prefix: longer input never changes prior output, no lookahead. */
 tone(1000);uint32_t prefix[64];CHECK(!af_filter(src,96000,prefix,64,32,AF_MA4_HP80,&sat));CHECK(!af_filter(src,96000,dst,96000,48000,AF_MA4_HP80,&sat));CHECK(!memcmp(prefix,dst,sizeof prefix));
 for(unsigned i=0;i<96000;i++)dst[i]=0x12345678u;
 sat=77;
 CHECK(af_filter(src,96000,dst,96000,0,AF_MA4,&sat)<0);
 CHECK(af_filter(src,96000,dst,96000,48001,AF_MA4,&sat)<0);
 CHECK(af_filter(src,1,dst,96000,1,AF_MA4,&sat)<0);
 CHECK(af_filter(src,96000,dst,1,1,AF_MA4,&sat)<0);
 CHECK(af_filter(src,96000,dst,96000,1,(enum af_mode)0,&sat)<0);
 CHECK(af_filter(NULL,96000,dst,96000,1,AF_MA4,&sat)<0);
 CHECK(af_filter(src,96000,dst,96000,1,AF_MA4,NULL)<0);
 CHECK(af_filter(src,96000,src,96000,1,AF_MA4,&sat)<0);
 CHECK(af_filter(src,96000,src+1,95999,2,AF_MA4,&sat)<0);
 CHECK(af_filter(src,96000,dst,96000,1,AF_MA4,src)<0);
 CHECK(af_filter(src,96000,dst,96000,1,AF_MA4,dst)<0);
 CHECK(af_filter((const uint32_t*)(const void*)((const unsigned char*)src+1),96000,dst,96000,1,AF_MA4,&sat)<0);
 CHECK(sat==77);for(unsigned i=0;i<96000;i++)CHECK(dst[i]==0x12345678u);
 CHECK(!af_filter(src,96000,dst,96000,1,AF_MA4,&sat));
 printf("PASS %u checks; pure host DSP, no hardware claims\n",checks);return 0;
}
