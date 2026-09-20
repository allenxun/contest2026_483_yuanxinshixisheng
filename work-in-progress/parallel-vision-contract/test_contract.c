#include "vision_contract.h"
#include "k7_track.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 1;} }while(0)
int main(void)
{
  struct vv_meta m={42,1000000,1100000,160,120,true,true};
  struct k7_faces_s a={.count=1,.face={{100,40,20,30,.9f}},.usec=90000},b;
  struct vv_result r;
  CHECK(vv_from_yunet(&m,0,&a,&r)==VV_VALID);
  CHECK(r.meta.published_us==1000000&&r.inference_us==90000&&r.meta.replay);
  CHECK(r.targets[0].center_x==110&&r.targets[0].center_y==55);
  CHECK(vv_tracking_input(&r,1250000,&b)==VV_VALID);
  CHECK(b.count==1&&!memcmp(&a.face[0],&b.face[0],sizeof(a.face[0])));
  CHECK(vv_tracking_input(&r,1250001,&b)==VV_STALE&&b.count==0);
  CHECK(vv_tracking_input(&r,1099999,&b)==VV_STALE);
  m.now_us=1250001;CHECK(vv_from_yunet(&m,0,&a,&r)==VV_STALE);
  m.now_us=999999;CHECK(vv_from_yunet(&m,0,&a,&r)==VV_STALE);
  m.now_us=1100000;m.monotonic_known=false;
  CHECK(vv_from_yunet(&m,0,&a,&r)==VV_TIME_UNKNOWN);
  m.monotonic_known=true;m.width=640;CHECK(vv_from_yunet(&m,0,&a,&r)==VV_INVALID);
  m.width=160;CHECK(vv_from_yunet(&m,-1,&a,&r)==VV_DETECTOR_ERROR);
  CHECK(vv_from_yunet(&m,0,NULL,&r)==VV_INVALID);
  CHECK(vv_from_yunet(NULL,0,&a,&r)==VV_INVALID);
  CHECK(vv_from_yunet(&m,0,&a,NULL)==VV_INVALID);
  a.count=17;CHECK(vv_from_yunet(&m,0,&a,&r)==VV_INVALID&&r.count==0);
  a.count=0;CHECK(vv_from_yunet(&m,0,&a,&r)==VV_EMPTY);
  CHECK(vv_tracking_input(&r,m.now_us,&b)==VV_EMPTY&&b.count==0);
  a.count=1;
  float bad[]={NAN,INFINITY,-INFINITY,-1,161};
  for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++) {
    a.face[0].x=bad[i];CHECK(vv_from_yunet(&m,0,&a,&r)==VV_INVALID&&r.count==0);
  }
  a.face[0]=(struct k7_face_s){0,0,160,120,1};
  CHECK(vv_from_yunet(&m,0,&a,&r)==VV_VALID);
  r.targets[0].center_x=NAN;CHECK(vv_tracking_input(&r,m.now_us,&b)==VV_INVALID&&b.count==0);
  a.face[0].width=0;CHECK(vv_from_yunet(&m,0,&a,&r)==VV_INVALID);
  a.face[0]=(struct k7_face_s){1,1,20,20,1.01f};
  CHECK(vv_from_yunet(&m,0,&a,&r)==VV_INVALID);
  a.face[0].score=.9f;a.count=16;
  for(unsigned i=1;i<16;i++)a.face[i]=a.face[0];
  CHECK(vv_from_yunet(&m,0,&a,&r)==VV_VALID&&r.count==16);
  a.face[15].height=NAN;CHECK(vv_from_yunet(&m,0,&a,&r)==VV_INVALID&&r.count==0);
  CHECK(vv_native_supported(VV_FACE)&&!vv_native_supported(VV_BODY)&&!vv_native_supported(VV_INSTRUMENT));
  CHECK(vv_unavailable(&m,VV_BODY,&r)==VV_UNSUPPORTED);
  CHECK(vv_tracking_input(&r,m.now_us,&b)==VV_UNSUPPORTED&&b.count==0);
  CHECK(vv_unavailable(&m,VV_INSTRUMENT,&r)==VV_UNSUPPORTED);
  float device[]={10,20,110,220};m.width=640;m.height=480;
  CHECK(vv_from_legacy_device(&m,0,device,.8f,&r)==VV_VALID);
  CHECK(r.source==VV_LEGACY_PC_DECODED&&r.targets[0].category==VV_INSTRUMENT&&r.targets[0].center_y==120);
  CHECK(vv_tracking_input(&r,m.now_us,&b)==VV_UNSUPPORTED&&b.count==0);
  CHECK(vv_from_legacy_device(&m,0,NULL,0,&r)==VV_EMPTY);
  CHECK(vv_from_legacy_device(&m,0,NULL,NAN,&r)==VV_INVALID);
  device[2]=9;CHECK(vv_from_legacy_device(&m,0,device,.8f,&r)==VV_INVALID);
  device[2]=INFINITY;CHECK(vv_from_legacy_device(&m,0,device,.8f,&r)==VV_INVALID);
  m.width=8193;CHECK(vv_from_legacy_device(&m,0,NULL,0,&r)==VV_INVALID);
  /* Real unmodified production tracker linked locally; synthetic replay only.
   * Compare direct and adapted outputs over 1000 frames including zero faces,
   * future/stale samples, duplicate timestamps, halted and low confidence. */
  struct k7_track_config_s cfg={.limit=100,.sign_x=1,.sign_y=-1,.axes=TRACK_XY};
  struct k7_track_s direct,adapted;
  CHECK(k7_track_init(&direct,&cfg,0,0)==0&&k7_track_init(&adapted,&cfg,0,0)==0);
  m.width=160;m.height=120;
  for(unsigned i=0;i<1000;i++) {
    m.now_us=2000000+(uint64_t)i*50000;
    m.published_us=m.now_us-10000;
    if(i%17==0)m.published_us=m.now_us-250001;
    if(i%29==0)m.published_us=m.now_us+1;
    a.count=i%11==0?0:1;
    a.face[0]=(struct k7_face_s){(float)(i%120),30,20,30,i%13==0?.5f:.9f};
    enum vv_status s=vv_from_yunet(&m,0,&a,&r);
    enum vv_status t=vv_tracking_input(&r,m.now_us,&b);
    struct k7_track_result_s x,y;
    k7_track_step(&direct,&a,m.now_us,m.published_us,i%19==0,&x);
    k7_track_step(&adapted,(t==VV_VALID||t==VV_EMPTY)?&b:NULL,m.now_us,m.published_us,i%19==0,&y);
    CHECK(s==t);
    CHECK(x.state==y.state&&x.update==y.update&&x.has_face==y.has_face&&x.x==y.x&&x.y==y.y&&x.dx==y.dx&&x.dy==y.dy);
    if(i%10==0) {
      k7_track_step(&direct,&a,m.now_us,m.published_us,false,&x);
      k7_track_step(&adapted,&b,m.now_us,m.published_us,false,&y);
      CHECK(x.state==y.state&&x.update==y.update&&x.x==y.x&&x.y==y.y);
      /* Halt is handled before stamps in production and does not consume a
       * sample; repeating a halted sample after resume is not a duplicate. */
      if(i%19!=0)CHECK(x.state==TRACK_STALE&&!y.update);
    }
  }
  printf("PASS %u checks; 1000 synthetic replay frames; production k7_track.c linked; no hardware/model inference\n",checks);
  return 0;
}
