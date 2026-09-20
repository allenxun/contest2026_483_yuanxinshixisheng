#ifndef PCM_OBSERVER_H
#define PCM_OBSERVER_H
#include <stdint.h>
#include <stddef.h>
#define PO_MAX_FRAMES 48000u /* 3 seconds only if actual rate is verified 16kHz */
#define PO_MAX_CHUNK 4096u
struct po_channel { int32_t min,max;int64_t sum;uint64_t sum_squares;uint32_t peak,clipped,nonzero; };
struct po_stats {uint32_t frames;struct po_channel channel[2];};
/* PCM16LE interleaved stereo only. Initialize once; single serialized owner.
 * No devices, allocation, gain, normalization, resampling or codec access. */
void po_init(struct po_stats *);
/* All-or-nothing: invalid chunk/limit leaves stats intact. */
int po_push(struct po_stats *,const unsigned char *,size_t);
/* Caller knows expected actual frame count; zero/partial capture fails. */
int po_complete(const struct po_stats *,uint32_t expected_frames);
#endif
