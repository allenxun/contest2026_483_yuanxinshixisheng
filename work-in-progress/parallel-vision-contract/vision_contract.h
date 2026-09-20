/* SPDX-License-Identifier: Apache-2.0 */
#ifndef VV_CANDIDATE_VISION_CONTRACT_H
#define VV_CANDIDATE_VISION_CONTRACT_H
#include "k7_yunet.h"
#include <stdbool.h>
#define VV_MAX_AGE_US 250000u
#define VV_MAX_DIM 8192u
enum vv_class { VV_FACE, VV_BODY, VV_INSTRUMENT };
enum vv_source { VV_NATIVE_YUNET, VV_LEGACY_PC_DECODED, VV_NATIVE_UNAVAILABLE };
enum vv_status { VV_VALID, VV_EMPTY, VV_INVALID, VV_STALE, VV_UNSUPPORTED,
                 VV_DETECTOR_ERROR, VV_TIME_UNKNOWN };
/* Caller supplies same-domain monotonic times; never use faces.usec or PC
 * timestamp_ms as publication time without an explicit clock conversion.
 * replay marks synthetic/replayed data, independently of interface source. */
struct vv_meta {
  uint64_t frame_id, published_us, now_us;
  unsigned width, height;
  bool monotonic_known, replay;
};
struct vv_target {
  enum vv_class category;
  float x, y, width, height, center_x, center_y, confidence;
};
struct vv_result {
  struct vv_meta meta;
  enum vv_source source;
  enum vv_class category;
  enum vv_status status;
  uint64_t inference_us;
  unsigned count;
  struct vv_target targets[K7_FACE_MAX];
};
bool vv_native_supported(enum vv_class category);
enum vv_status vv_from_yunet(const struct vv_meta *, int detector_ret,
                            const struct k7_faces_s *, struct vv_result *);
/* Only runtime.infer_bytes device_bbox xyxy/device_score, already rescaled to
 * exif_normalized_unmirrored_original. NULL bbox means no detection.
 * Not raw ONNX/RKNN tensors, not a model runner. No body decoder exists. */
enum vv_status vv_from_legacy_device(const struct vv_meta *, int detector_ret,
                                    const float bbox[4], float device_score,
                                    struct vv_result *);
enum vv_status vv_unavailable(const struct vv_meta *, enum vv_class,
                             struct vv_result *);
/* Candidate tracking input only: exact face roundtrip, no scaling or target
 * selection. At consumption recheck age. Always zero output on rejection.
 * Caller must call existing k7_track_step with NULL on any non VALID/EMPTY
 * result so previous tracking state resets; never silently retain old boxes. */
enum vv_status vv_tracking_input(const struct vv_result *, uint64_t now_us,
                                 struct k7_faces_s *);
#endif
