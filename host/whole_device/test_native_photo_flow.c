/* Actual capture gate + RAM retention; simulated decoder/pose only. */
#include <assert.h>
#include <time.h>
static unsigned long long fake_ms=1000;
static int simulated_clock(clockid_t id,struct timespec *t)
{(void)id;t->tv_sec=fake_ms/1000;t->tv_nsec=(fake_ms%1000)*1000000;return 0;}
#define clock_gettime simulated_clock
#include "../../app/k7host/k7_photo.c"
#undef clock_gettime
struct k7_pose_s {int dummy;};
static float yaw;
struct k7_pose_s *k7_pose_create(void){return calloc(1,sizeof(struct k7_pose_s));}
void k7_pose_destroy(struct k7_pose_s *p){free(p);}
int k7_pose_infer(struct k7_pose_s *p,const float input[12288],float output[3])
{(void)p;(void)input;output[0]=yaw;output[1]=0;output[2]=0;return 0;}
int k7_jpeg_decode(const uint8_t *data,size_t size,unsigned scale,uint8_t *rgb,size_t cap,struct k7_jpeg_result_s *out)
{
  (void)data;(void)size;(void)scale;assert(cap>=640*480*3);
  uint32_t x=17;
  for(unsigned i=0;i<640*480*3;i++){x=x*1664525u+1013904223u;rgb[i]=x>>24;}
  *out=(struct k7_jpeg_result_s){.width=640,.height=480};return 0;
}
int main(void)
{
  struct k7_photo_s *p=k7_photo_create_native();assert(p);
  struct k7_track_result_s track={.state=TRACK_ACTIVE,.has_face=true,
                                 .box={.x=40,.y=20,.width=70,.height=70}};
  uint8_t jpeg[]={0xff,0xd8,3,4,0xff,0xd9},saved[20];unsigned seq=0;
  /* An external host ACK is not allowed to fabricate native retention. */
  k7_photo_ack(1,p->epoch,1,true);
  for(unsigned side=0;side<3;side++)
    {
      yaw=side==0?0:side==1?45:-45;
      for(unsigned n=0;n<30 && !(p->gate.done&(1u<<side));n++)
        {
          fake_ms+=100;
          k7_photo_process(p,jpeg,sizeof(jpeg),++seq,fake_ms*1000,&track,1,false);
        }
      assert(p->gate.done&(1u<<side));
      uint32_t actual_epoch;unsigned actual_done;
      assert(!k7_photo_native_status(&actual_epoch,&actual_done));
      assert(actual_epoch==p->epoch && actual_done==((1u<<(side+1))-1));
      struct k7_photo_record r;
      assert(!k7_photo_native_copy(p->epoch,1u<<side,&r,saved,sizeof(saved)));
      assert(r.epoch==p->epoch && r.side==(1u<<side) && r.bytes==sizeof(jpeg));
      assert(!memcmp(jpeg,saved,sizeof(jpeg)));
    }
  assert(k7_photo_native_complete(p->epoch)==1);
  unsigned old=p->epoch;k7_photo_reset();fake_ms+=100;
  k7_photo_process(p,jpeg,sizeof(jpeg),++seq,fake_ms*1000,&track,1,true);
  assert(k7_photo_native_complete(old)==-ESTALE);
  assert(!p->gate.done);
  k7_photo_destroy(p);
  assert(k7_photo_native_complete(old)==-ENODEV);
  puts("native gate to exact RAM photos PASS; simulated images, not hardware acceptance");
}
