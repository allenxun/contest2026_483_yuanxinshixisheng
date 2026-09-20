#ifndef K7_CAPTURE_STREAM_H
#define K7_CAPTURE_STREAM_H
#include "pio.h"
/* Dedicated capture task holds the existing codec owner lock. A successful
 * call delivers exactly frames real samples; error/cancel invalidates the
 * utterance. Current audited window is 320..48000 (20 ms..3 s), step 320.
 * Codec setup includes its existing settling delay. Connect and await network
 * readiness before starting; UI readiness must account for codec settling. */
int k7sound_capture_stream(unsigned frames, pio_sample_sink sink, void *arg);
/* Settle ADC before the audible cue, then capture under the same owner lock. */
int k7sound_capture_stream_cued(unsigned frames,pio_sample_sink sink,void *arg);
#endif
