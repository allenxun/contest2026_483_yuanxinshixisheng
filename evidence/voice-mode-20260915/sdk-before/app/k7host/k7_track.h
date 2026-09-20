/* SPDX-License-Identifier: Apache-2.0 */
#ifndef K7_TRACK_H
#define K7_TRACK_H
#include <stdbool.h>
#include <stdint.h>
#include "k7_yunet.h"
enum k7_track_axes_e { TRACK_X = 1, TRACK_Y = 2, TRACK_XY = 3 };
struct k7_track_config_s {
  bool transmit; int limit, sign_x, sign_y; unsigned int axes; bool preview;
  bool calibrated; bool photo;
  int min_x, max_x, min_y, max_y, center_x, center_y;
};
enum k7_track_state_e { TRACK_LOST, TRACK_CONFIRM, TRACK_ACTIVE, TRACK_STALE, TRACK_HALTED, TRACK_CLIPPED, TRACK_STATE_COUNT };
struct k7_track_s
{
  struct k7_track_config_s config;
  struct k7_face_s previous;
  bool have_previous;
  unsigned int hits_x, hits_y;
  unsigned int edge_y, edge_y_hits;
  float filtered_x, filtered_y, target_x, target_y;
  uint64_t previous_time, previous_sample;
  int sent_x, sent_y;
};
struct k7_track_result_s
{
  enum k7_track_state_e state;
  bool update;
  int x, y;
  float dx, dy;
  bool has_face;
  struct k7_face_s box;
  unsigned int edges; /* left=1, top=2, right=4, bottom=8 */
};
int k7_track_init(struct k7_track_s *, const struct k7_track_config_s *,
                  int initial_x, int initial_y);
void k7_track_step(struct k7_track_s *, const struct k7_faces_s *,
                    uint64_t now, uint64_t sample, bool halted,
                    struct k7_track_result_s *);
#endif
