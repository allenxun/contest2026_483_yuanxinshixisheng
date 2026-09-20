#include "fusion_core.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
static struct vf_config c={45,7,12,3,80,60,500,350,700,500,1,13};
static struct vf_frame f;
static struct vf_state s;
static struct vf_result tick(float yaw)
{
  f.frame_id++;f.captured_ms+=100;f.now_ms=f.captured_ms+20;
  f.raw_pose=f.filtered_pose=(struct vf_pose){yaw,0,0,true};
  return vf_step(&s,&f);
}
static void init(void)
{
  assert(vf_init(&s,&c,1)==0);
  f=(struct vf_frame){.lock_epoch=1,.face_locked=true,.gimbal_settled=true,
                     .face_size=100,.sharpness=100,.spare_inference_budget=true};
}
static struct vf_result stable(float yaw)
{struct vf_result r={0};for(int i=0;i<6;i++)r=tick(yaw);return r;}
int main(void)
{
  init(); struct vf_result r=stable(0); assert(r.shot==VF_FRONT);
  assert(!vf_saved(&s,r.frame_id+1,1,VF_FRONT,true));
  assert(s.pending && !s.done);
  assert(vf_saved(&s,r.frame_id,1,VF_FRONT,false));assert(!s.done);
  r=stable(0); assert(r.shot==VF_FRONT);
  assert(vf_saved(&s,r.frame_id,1,r.shot,true));
  r=stable(0); assert(r.shot==VF_NONE);
  r=stable(45);assert(r.shot==VF_LEFT);
  assert(vf_saved(&s,r.frame_id,1,r.shot,true));
  r=stable(-45);assert(r.shot==VF_RIGHT);
  assert(vf_saved(&s,r.frame_id,1,r.shot,true));
  assert(tick(45).reason==VF_COMPLETE);
  init(); for(int i=0;i<5;i++)tick(-45);
  f.frame_id++;f.captured_ms+=100;f.now_ms=f.captured_ms;
  f.raw_pose.yaw=-80;r=vf_step(&s,&f);assert(r.shot==VF_NONE);
  assert(s.samples==0); /* no filtered-angle false capture */
  init();f.ambiguous=true;assert(stable(0).reason==VF_TARGET_CHANGED);
  init();f.lock_epoch=2;assert(stable(0).reason==VF_TARGET_CHANGED);
  init();f.gimbal_settled=false;assert(stable(0).reason==VF_QUALITY);
  init();f.sharpness=NAN;assert(stable(0).reason==VF_QUALITY);
  init();tick(0);assert(vf_step(&s,&f).reason==VF_STALE);
  f.frame_id++;f.captured_ms++;f.now_ms=f.captured_ms+701;
  assert(vf_step(&s,&f).reason==VF_STALE);
  init();for(int i=0;i<5;i++)tick(0);f.captured_ms+=400;
  assert(tick(0).shot==VF_NONE && s.samples==1);
  init();f.object_busy=true;assert(!tick(0).request_object);
  f.object_busy=false;f.spare_inference_budget=false;assert(!tick(0).request_object);
  f.spare_inference_budget=true;assert(tick(0).request_object);
  assert(!tick(0).request_object);
  init();assert(stable(32).shot==VF_LEFT);
  init();assert(stable(58).shot==VF_LEFT);
  init();assert(stable(-32).shot==VF_RIGHT);
  init();assert(stable(-58).shot==VF_RIGHT);
  init();assert(stable(-31.9f).shot==VF_NONE);
  init();assert(stable(-58.1f).shot==VF_NONE);
  init();assert(stable(31.9f).shot==VF_NONE);
  init();assert(stable(58.1f).shot==VF_NONE);
  init();assert(stable(7).shot==VF_FRONT);
  init();assert(stable(7.1f).shot==VF_NONE);
  init();assert(stable(-7).shot==VF_FRONT);
  init();assert(stable(-7.1f).shot==VF_NONE);
  c.side_tolerance=NAN;assert(vf_init(&s,&c,1)<0);c.side_tolerance=13;
  c.tolerance=25;assert(vf_init(&s,&c,1)<0);
  puts("PASS: three views, same-frame commit, save retry, duplicates, raw-pose gate,");
  puts("lock change, ambiguity, movement, quality, stale/gaps, bounded object dispatch.");
}
