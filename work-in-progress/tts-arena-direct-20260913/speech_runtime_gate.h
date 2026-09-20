#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* ASR and TTS share one non-recursive arena and must never overlap. */
int k7_speech_runtime_try_acquire(void);
void k7_speech_runtime_release(void);

#ifdef __cplusplus
}
#endif
