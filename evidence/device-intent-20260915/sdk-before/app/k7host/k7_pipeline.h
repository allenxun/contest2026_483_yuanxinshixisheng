/* SPDX-License-Identifier: Apache-2.0 */
#ifndef K7_PIPELINE_H
#define K7_PIPELINE_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "k7_yunet.h"
#include "k7_track.h"
struct k7_pipeline_s;
struct k7_pipeline_stats_s
{
  unsigned int published, decoded, failed, dropped, peak_pending;
  unsigned int last_sequence, width, height;
  size_t bytes;
  uint64_t decode_us, max_decode_us, max_age_us, elapsed_us;
  int last_error;
  unsigned int face_inferences, face_frames, face_failures, last_face_count;
  uint64_t inference_us, max_inference_us;
  struct k7_face_s primary;
  unsigned int track_observations, track_updates, track_tx, track_errors;
  unsigned int track_states[TRACK_STATE_COUNT], track_max_step;
  int track_x, track_y;
  int track_error;

};
/* Single producer, one decoder. Caller keeps RGB alive through finish.
 * finish joins the worker before releasing its private JPEG slots.
 * Age starts at publication by the parser, NOT sensor exposure time.
 */
int k7_pipeline_start(struct k7_pipeline_s **out, size_t jpeg_capacity,
                      unsigned int scale, unsigned int delay_ms,
                      uint8_t *rgb, size_t rgb_capacity, bool detect_faces,
                      const struct k7_track_config_s *track);
/* Halt stops future visual target updates, not MCU PWM or already queued bytes. */
void k7_pipeline_halt(void);
/* Voice session modes: 0 hold, 1 tracking, 2 photo. Does not reopen UVC.
 * Return 0 means accepted; VOICE MODE applied is emitted by the worker.
 */
int k7_pipeline_voice_mode(unsigned int mode);
void k7_pipeline_publish(struct k7_pipeline_s *p,
                         const uint8_t *jpeg, size_t bytes);
int k7_pipeline_finish(struct k7_pipeline_s *p,
                       struct k7_pipeline_stats_s *stats);
#endif
