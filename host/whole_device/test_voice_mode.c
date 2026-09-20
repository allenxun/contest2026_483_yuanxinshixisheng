/* Exercise the actual firmware mode transition code without hardware. */
#include <assert.h>
#include "../../app/k7host/k7_pipeline.c"
static unsigned resets;
static bool needs_restart;
bool k7_photo_needs_restart(void) { return needs_restart; }
void k7_photo_reset(void) { resets++; needs_restart=false; }
int main(void)
{
  struct k7_pipeline_s p = {0};
  struct k7_track_config_s config = {.axes=TRACK_XY, .limit=100,
                                    .sign_x=1, .sign_y=-1};
  p.voice_control = true;
  assert(k7_track_init(&p.controller, &config, 0, 0) == 0);
  assert(k7_pipeline_voice_mode(1) == -ENODEV);
  assert(k7_pipeline_voice_mode_status(1) == -ENODEV);
  g_voice_active = true;
  atomic_store(&g_track_halt, true);
  assert(k7_pipeline_voice_mode(3) == -EINVAL);
  assert(k7_pipeline_voice_mode(1) == 0);
  assert(atomic_load(&g_track_halt)); /* Acceptance is not applied readiness. */
  assert(k7_pipeline_voice_mode_status(1) == -EAGAIN);
  voice_mode_apply(&p);
  assert(!atomic_load(&g_track_halt));
  assert(p.applied_mode == 1);
  assert(k7_pipeline_voice_mode_status(1) == 0);
  p.controller.hits_x = 99;
  k7_pipeline_halt();
  assert(atomic_load(&g_track_halt));
  /* Stop and restart can arrive before another frame is decoded. */
  assert(k7_pipeline_voice_mode(1) == 0);
  voice_mode_apply(&p);
  assert(!atomic_load(&g_track_halt));
  assert(p.controller.hits_x == 0);
  assert(k7_pipeline_voice_mode(2) == 0);
  voice_mode_apply(&p);
  assert(resets == 1);
  assert(k7_pipeline_voice_mode(2) == 0);
  voice_mode_apply(&p);
  assert(resets == 1); /* Duplicate command must not discard saved photos. */
  needs_restart=true;
  assert(k7_pipeline_voice_mode(2)==0);
  assert(k7_pipeline_voice_mode_status(2)==-EAGAIN);
  voice_mode_apply(&p);
  assert(resets==2 && !needs_restart);
  assert(k7_pipeline_voice_mode_status(2)==0);
  assert(k7_pipeline_voice_mode(2)==0);
  voice_mode_apply(&p);
  assert(resets==2);
  k7_pipeline_halt();
  voice_mode_apply(&p);
  assert(p.applied_mode == 0 && atomic_load(&g_track_halt));
  unsigned ticket;
  assert(k7_pipeline_hold_revision(&ticket)==0);
  k7_pipeline_halt();
  assert(k7_pipeline_resume_tracking(ticket)==-ECANCELED);
  voice_mode_apply(&p);
  assert(k7_pipeline_hold_revision(&ticket)==0);
  assert(k7_pipeline_resume_tracking(ticket)==0);
  assert(atomic_load(&g_track_halt));
  assert(k7_pipeline_voice_mode_status(1)==-EAGAIN);
  voice_mode_apply(&p);
  assert(!atomic_load(&g_track_halt));
  assert(k7_pipeline_resume_tracking(ticket)==-ECANCELED);
  k7_pipeline_halt();voice_mode_apply(&p);
  p.stats.track_error = -EIO;
  assert(k7_pipeline_voice_mode(1) == 0);
  voice_mode_apply(&p);
  assert(atomic_load(&g_track_halt));
  assert(p.applied_mode == 0);
  assert(k7_pipeline_voice_mode_status(1) == -EIO);
  puts("voice mode transitions: PASS");
  return 0;
}
