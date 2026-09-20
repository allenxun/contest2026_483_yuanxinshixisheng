#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Synchronous bounded helpers for the VoiceLink coordinator. */
int k7sound_capture_grouped(unsigned frames);
int k7sound_play_prompt_tone(void);
/* Immutable interleaved stereo S32 at 16 kHz, at most 30 seconds. Optional
 * capture is armed/settled before speech and starts immediately after playback.
 * The caller retains the buffer until this synchronous operation returns. */
int k7sound_speak_pcm(const uint32_t *pcm, unsigned frames,
                      unsigned capture_frames);

#ifdef __cplusplus
}
#endif
