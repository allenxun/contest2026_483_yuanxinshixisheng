/* SPDX-License-Identifier: Apache-2.0 */
#include "vision_contract.h"
#include <math.h>
#include <string.h>
static enum vv_status begin(const struct vv_meta *m, enum vv_source source,
                            enum vv_class category, struct vv_result *r)
{
  if (!r) return VV_INVALID;
  memset(r,0,sizeof(*r));
  r->source=source; r->category=category; r->status=VV_INVALID;
  if (!m) return r->status;
  r->meta=*m;
  if (!m->width || !m->height || m->width>VV_MAX_DIM || m->height>VV_MAX_DIM)
    return r->status;
  if (!m->monotonic_known) return r->status=VV_TIME_UNKNOWN;
  if (m->published_us>m->now_us || m->now_us-m->published_us>VV_MAX_AGE_US)
    return r->status=VV_STALE;
  return r->status=VV_EMPTY;
}
static bool box_ok(float x,float y,float w,float h,float score,unsigned iw,unsigned ih)
{
  return isfinite(x)&&isfinite(y)&&isfinite(w)&&isfinite(h)&&isfinite(score)&&
    x>=0&&y>=0&&w>0&&h>0&&score>=0&&score<=1&&x+w<=iw&&y+h<=ih;
}
static struct vv_target target(enum vv_class c,float x,float y,float w,float h,float s)
{ return (struct vv_target){c,x,y,w,h,x+w/2,y+h/2,s}; }
bool vv_native_supported(enum vv_class c) { return c==VV_FACE; }
enum vv_status vv_from_yunet(const struct vv_meta *m,int ret,
                            const struct k7_faces_s *f,struct vv_result *r)
{
  enum vv_status s=begin(m,VV_NATIVE_YUNET,VV_FACE,r);
  if(s!=VV_EMPTY)return s;
  if(m->width!=160||m->height!=120)return r->status=VV_INVALID;
  if(ret!=0)return r->status=VV_DETECTOR_ERROR;
  if(!f||f->count>K7_FACE_MAX)return r->status=VV_INVALID;
  /* Validate whole frame before publishing any target. */
  for(unsigned i=0;i<f->count;i++) {
    const struct k7_face_s *b=&f->face[i];
    if(!box_ok(b->x,b->y,b->width,b->height,b->score,160,120))return r->status=VV_INVALID;
  }
  for(unsigned i=0;i<f->count;i++) {
    const struct k7_face_s *b=&f->face[i];
    r->targets[i]=target(VV_FACE,b->x,b->y,b->width,b->height,b->score);
  }
  r->inference_us=f->usec;r->count=f->count;
  return r->status=f->count?VV_VALID:VV_EMPTY;
}
enum vv_status vv_from_legacy_device(const struct vv_meta *m,int ret,
                                    const float b[4],float score,struct vv_result *r)
{
  enum vv_status s=begin(m,VV_LEGACY_PC_DECODED,VV_INSTRUMENT,r);
  if(s!=VV_EMPTY)return s;
  if(ret!=0)return r->status=VV_DETECTOR_ERROR;
  if(!b)return r->status=score==0?VV_EMPTY:VV_INVALID;
  if(!box_ok(b[0],b[1],b[2]-b[0],b[3]-b[1],score,m->width,m->height))
    return r->status=VV_INVALID;
  r->targets[0]=target(VV_INSTRUMENT,b[0],b[1],b[2]-b[0],b[3]-b[1],score);
  r->count=1;return r->status=VV_VALID;
}
enum vv_status vv_unavailable(const struct vv_meta *m,enum vv_class c,struct vv_result *r)
{
  if(!r)return VV_INVALID;
  (void)begin(m,VV_NATIVE_UNAVAILABLE,c,r);
  return r->status=VV_UNSUPPORTED;
}
enum vv_status vv_tracking_input(const struct vv_result *r,uint64_t now,struct k7_faces_s *f)
{
  if(!f)return VV_INVALID;
  memset(f,0,sizeof(*f));
  if(!r)return VV_INVALID;
  if(r->source!=VV_NATIVE_YUNET||r->category!=VV_FACE)return VV_UNSUPPORTED;
  if(r->status!=VV_VALID&&r->status!=VV_EMPTY)return r->status;
  if(!r->meta.monotonic_known)return VV_TIME_UNKNOWN;
  if(now<r->meta.now_us||r->meta.published_us>now||now-r->meta.published_us>VV_MAX_AGE_US)
    return VV_STALE;
  if(r->meta.width!=160||r->meta.height!=120||r->count>K7_FACE_MAX||
     (r->status==VV_EMPTY)!=(r->count==0))return VV_INVALID;
  for(unsigned i=0;i<r->count;i++) {
    const struct vv_target *b=&r->targets[i];
    if(b->category!=VV_FACE||!box_ok(b->x,b->y,b->width,b->height,b->confidence,160,120)||
       b->center_x!=b->x+b->width/2||b->center_y!=b->y+b->height/2)return VV_INVALID;
  }
  for(unsigned i=0;i<r->count;i++) {
    const struct vv_target *b=&r->targets[i];
    f->face[i]=(struct k7_face_s){b->x,b->y,b->width,b->height,b->confidence};
  }
  f->count=r->count;f->usec=r->inference_us;return r->status;
}
