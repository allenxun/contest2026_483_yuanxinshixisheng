/* SPDX-License-Identifier: Apache-2.0 */
#include "k7_track.h"
#include <errno.h>
#include <math.h>
#include <string.h>
/* MCU target units, not degrees. Keep physical range in the run config. */
#define FILTER_NEW 0.75f
#define X_DEADBAND 0.03f
#define Y_DEADBAND 0.04f
#define X_GAIN 200.0f /* Linux integrator 20/sample, normalized at 10Hz */
#define Y_GAIN 120.0f /* Linux integrator 12/sample, normalized at 10Hz */
#define X_PROPORTIONAL 70.0f
#define Y_PROPORTIONAL 45.0f
#define MAX_STEP 25.0f /* Linux target-step cap; also enforce a time-based slew */
#define SLEW_RATE 250.0f
#define Y_EDGE_RATE 60.0f /* slower than full correction; legacy units/sec */
static float clamp(float x, float lo, float hi)
{ return fmaxf(lo, fminf(hi, x)); }
static float correction(float filtered, float raw, float deadband)
{
  /* Old filter history must not command motion in the wrong direction
   * when the latest observation has already crossed the image center.
   * Removing the deadband width makes its boundary continuous.
   */
  if (filtered*raw <= 0) return 0;
  return copysignf(fmaxf(fabsf(filtered)-deadband,0),filtered);
}
static float axis_pi(float *integral, float error, float seconds,
                     float gain, float proportional, int sign, int sent,
                     float low, float high)
{
  /* Keep the integral in MCU command units; no frame-rate-dependent gain.
   * The proportional term reacts immediately to the latest image offset.
   * Back-calculation prevents accumulating an unreachable integral at a limit.
   */
  float p=error*proportional*sign;
  if (error==0) { *integral=sent; return (float)sent; }
  float next=clamp(*integral+error*gain*seconds*sign,low,high);
  float demand=clamp(next+p,low,high);
  if (demand != next+p) next=clamp(demand-p,low,high);
  *integral=next;
  float step=fminf(MAX_STEP,SLEW_RATE*seconds);
  return clamp((float)sent+clamp(demand-sent,-step,step),low,high);
}
static float iou(const struct k7_face_s *a, const struct k7_face_s *b)
{
  float w = fminf(a->x+a->width,b->x+b->width)-fmaxf(a->x,b->x);
  float h = fminf(a->y+a->height,b->y+b->height)-fmaxf(a->y,b->y);
  float intersect = fmaxf(w,0)*fmaxf(h,0);
  return intersect/(a->width*a->height+b->width*b->height-intersect);
}
static bool valid(const struct k7_face_s *f)
{
  return isfinite(f->x) && isfinite(f->y) && isfinite(f->width) &&
    isfinite(f->height) && isfinite(f->score) && f->score >= .7f &&
    f->score <= 1 && f->x >= 0 && f->y >= 0 &&
    f->width > 0 && f->height > 0 &&
    f->x+f->width <= 160.01f && f->y+f->height <= 120.01f;
}
int k7_track_init(struct k7_track_s *s, const struct k7_track_config_s *c,
                  int x, int y)
{
  if (!s || !c ||
      c->axes < TRACK_X || c->axes > TRACK_XY ||
      (c->sign_x != -1 && c->sign_x != 1) ||
      (c->sign_y != -1 && c->sign_y != 1))
    return -EINVAL;
  if (c->calibrated)
    {
      if (c->min_x < -800 || c->min_x > 800 || c->max_x < -800 || c->max_x > 800 ||
          c->min_y < -120 || c->min_y > 1030 || c->max_y < -120 || c->max_y > 1030 ||
          c->center_x < c->min_x+20 || c->center_x > c->max_x-20 ||
          c->center_y < c->min_y+20 || c->center_y > c->max_y-20 ||
          x < c->min_x || x > c->max_x || y < c->min_y || y > c->max_y)
        return -EINVAL;
    }
  else if (c->limit < 1 || c->limit > 150 ||
           x < -c->limit || x > c->limit || y < -c->limit ||
           y > c->limit || y < -120) return -EINVAL;
  memset(s,0,sizeof(*s)); s->config=*c;
  s->target_x=s->sent_x=x; s->target_y=s->sent_y=y;
  return 0;
}
void k7_track_step(struct k7_track_s *s, const struct k7_faces_s *faces,
                    uint64_t now, uint64_t sample, bool halted,
                    struct k7_track_result_s *out)
{
  *out=(struct k7_track_result_s){.state=TRACK_LOST,.x=s->sent_x,.y=s->sent_y};
  if (halted) { out->state=TRACK_HALTED; goto reset; }
  if (sample > now || now-sample > 250000 ||
      (s->previous_sample && sample <= s->previous_sample) ||
      (s->previous_time && now <= s->previous_time))
    { out->state=TRACK_STALE; goto reset; }
  bool gap=s->previous_time && now-s->previous_time > 400000;
  uint64_t dt=s->previous_time && !gap ? now-s->previous_time : 0;
  s->previous_sample=sample; s->previous_time=now;
  if (gap) { s->have_previous=false; s->hits_x=0; s->hits_y=0;
             s->edge_y=0; s->edge_y_hits=0; }
  if (!faces || faces->count > K7_FACE_MAX) goto reset;
  int chosen=-1;
  float best=-1;
  if (s->have_previous)
    for (unsigned i=0;i<faces->count;i++)
      if (valid(&faces->face[i]))
        {
          float score=iou(&s->previous,&faces->face[i]);
          if (score >= .15f && score > best) { chosen=i;best=score; }
        }
  if (chosen < 0)
    {
      s->hits_x=0; s->hits_y=0; s->filtered_x=0; s->filtered_y=0;
      s->edge_y=0; s->edge_y_hits=0;
      for (unsigned i=0;i<faces->count;i++)
        if (valid(&faces->face[i]))
          {
            const struct k7_face_s *f=&faces->face[i];
            float dx=f->x+f->width/2-80,dy=f->y+f->height/2-60;
            float priority=f->width*f->height*f->score*
              (1.25f-.25f*fminf(sqrtf(dx*dx+dy*dy)/100,1));
            if(priority>best) {chosen=i;best=priority;}
          }
    }
  if (chosen < 0) goto reset;
  out->has_face=true;
  out->box=faces->face[chosen];
  out->dx=out->box.x+out->box.width/2-80;
  out->dy=out->box.y+out->box.height/2-60;
  out->edges=(out->box.x <= 0 ? 1u:0) |
             (out->box.y <= 0 ? 2u:0) |
             (out->box.x+out->box.width >= 160 ? 4u:0) |
             (out->box.y+out->box.height >= 120 ? 8u:0);
  /* X still requires a complete extent. On Y, a single clipped edge with
   * an off-center visible box provides a direction, not a full error size.
   * Require three consecutive observations of the same edge, then use a
   * bounded slow rate to recover. A box spanning both Y edges is ambiguous.
   */
  bool valid_x=(s->config.axes & TRACK_X) && !(out->edges & 5u);
  bool valid_y=(s->config.axes & TRACK_Y) && !(out->edges & 10u);
  unsigned int y_edge=out->edges & 10u;
  bool recover_y=(s->config.axes & TRACK_Y) &&
    ((y_edge==8u && out->dy>60*Y_DEADBAND) ||
     (y_edge==2u && out->dy < -60*Y_DEADBAND));
  if (recover_y)
    {
      if (s->edge_y != y_edge)
        { s->edge_y_hits=0; s->target_y=s->sent_y; }
      s->edge_y=y_edge;
      if (s->edge_y_hits<3) s->edge_y_hits++;
    }
  else { s->edge_y=0; s->edge_y_hits=0; }
  s->previous=faces->face[chosen]; s->have_previous=true;
  out->dx=s->previous.x+s->previous.width/2-80;
  out->dy=s->previous.y+s->previous.height/2-60;
  if (valid_x)
    {
      if (s->hits_x < 2) s->hits_x++;
      s->filtered_x=(1-FILTER_NEW)*s->filtered_x+FILTER_NEW*out->dx/80;
    }
  else
    {
      s->hits_x=0; s->filtered_x=0; s->target_x=s->sent_x;
    }
  if (valid_y)
    {
      if (s->hits_y < 2) s->hits_y++;
      s->filtered_y=(1-FILTER_NEW)*s->filtered_y+FILTER_NEW*out->dy/60;
    }
  else
    {
      s->hits_y=0; s->filtered_y=0;
      if (!recover_y) s->target_y=s->sent_y;
    }
  if (!valid_x && !valid_y && !recover_y) {out->state=TRACK_CLIPPED;return;}
  if (s->hits_x < 2 && s->hits_y < 2 && s->edge_y_hits<3)
    {out->state=TRACK_CONFIRM;return;}
  out->state=TRACK_ACTIVE;
  /* The legacy MCU's negative Y command hits 500us near -133 units.
   * Keep margin at -120; a symmetric large range would wind up at the MCU.
   * X +/-800 maps to 2452..532us with MCU v1.3 MID=1492.
   */
  float seconds=fminf((float)dt/1000000,.2f);
  float low_x=s->config.calibrated ? s->config.min_x : -s->config.limit;
  float high_x=s->config.calibrated ? s->config.max_x : s->config.limit;
  float low_y=s->config.calibrated ? s->config.min_y : fmaxf(-s->config.limit,-120);
  float high_y=s->config.calibrated ? s->config.max_y : s->config.limit;
  float x=s->sent_x,y=s->sent_y;
  if (s->hits_x>=2)
    x=axis_pi(&s->target_x,correction(s->filtered_x,out->dx,X_DEADBAND),
              seconds,X_GAIN,X_PROPORTIONAL,s->config.sign_x,s->sent_x,
              low_x,high_x);
  if (s->hits_y>=2)
    y=axis_pi(&s->target_y,correction(s->filtered_y,out->dy,Y_DEADBAND),
              seconds,Y_GAIN,Y_PROPORTIONAL,s->config.sign_y,s->sent_y,
              low_y,high_y);
  if (recover_y && s->edge_y_hits>=3)
    {
      s->target_y=clamp(s->target_y+copysignf(Y_EDGE_RATE*seconds,out->dy)*
                         s->config.sign_y,low_y,high_y);
      y=s->target_y;
    }
  out->x=(int)lroundf(x);out->y=(int)lroundf(y);
  out->update=out->x!=s->sent_x || out->y!=s->sent_y;
  s->sent_x=out->x;s->sent_y=out->y;
  return;
reset:
  s->have_previous=false;s->hits_x=0;s->hits_y=0;s->filtered_x=0;s->filtered_y=0;
  s->edge_y=0;s->edge_y_hits=0;
  /* Freeze at last requested position, not at a mechanical zero. */
  s->target_x=s->sent_x;s->target_y=s->sent_y;
}
