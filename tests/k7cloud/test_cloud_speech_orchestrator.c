#include "cloud_speech_orchestrator.h"

#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); return 1; \
} } while (0)

struct fake {
  int prompt_calls, asr_calls, tts_calls, play_calls;
  int prompt_rc, asr_rc, tts_rc, play_rc;
  int drop_link_during_asr, oversize_tts;
  size_t last_wav_bytes, played_frames;
  int16_t played[16];
  unsigned tts_rate;
  struct cloud_speech_orchestrator *owner;
};

static void put16(unsigned char *p, unsigned v) {
  p[0] = (unsigned char)v; p[1] = (unsigned char)(v >> 8);
}

static void put32(unsigned char *p, unsigned v) {
  p[0] = (unsigned char)v; p[1] = (unsigned char)(v >> 8);
  p[2] = (unsigned char)(v >> 16); p[3] = (unsigned char)(v >> 24);
}

static size_t wav(unsigned char *out, unsigned rate, const int16_t *pcm,
                  size_t frames) {
  size_t bytes = frames * 2;
  memcpy(out, "RIFF", 4); put32(out + 4, (unsigned)bytes + 36);
  memcpy(out + 8, "WAVEfmt ", 8); put32(out + 16, 16);
  put16(out + 20, 1); put16(out + 22, 1); put32(out + 24, rate);
  put32(out + 28, rate * 2); put16(out + 32, 2); put16(out + 34, 16);
  memcpy(out + 36, "data", 4); put32(out + 40, (unsigned)bytes);
  for (size_t i = 0; i < frames; ++i) put16(out + 44 + i * 2,
                                             (uint16_t)pcm[i]);
  return 44 + bytes;
}

static int prompt(void *arg, enum cloud_speech_prompt which) {
  struct fake *f = arg;
  CHECK(which == CLOUD_SPEECH_PROMPT_NETWORK_CONNECTED);
  ++f->prompt_calls;
  return f->prompt_rc;
}

static int asr(void *arg, const char *token, const unsigned char *data,
               size_t bytes, char *text, size_t cap, size_t *text_bytes,
               bool (*cancelled)(void *), void *cancel_arg) {
  struct fake *f = arg;
  ++f->asr_calls; f->last_wav_bytes = bytes;
  CHECK(!strcmp(token, "runtime-token"));
  CHECK(bytes >= 46 && !memcmp(data, "RIFF", 4));
  CHECK(cap >= 3);
  CHECK(cancelled && !cancelled(cancel_arg));
  if (f->owner) CHECK(f->owner->busy);
  if (f->asr_rc) return f->asr_rc;
  memcpy(text, "ok", 3); *text_bytes = 2;
  if (f->drop_link_during_asr)
    CHECK(cloud_speech_set_network(f->owner, false, false) == 0);
  return 0;
}

static int tts(void *arg, const char *token, const char *text,
               const char *voice, unsigned char *out, size_t cap,
               size_t *bytes, bool (*cancelled)(void *), void *cancel_arg) {
  static const int16_t pcm24[] = {0, 300, 600, 900, 1200, 1500};
  static const int16_t pcm16[] = {-7, 8, 9};
  struct fake *f = arg;
  ++f->tts_calls;
  CHECK(!strcmp(token, "runtime-token"));
  CHECK(!strcmp(text, "hello") && !strcmp(voice, "male"));
  CHECK(cap >= 56);
  CHECK(cancelled && !cancelled(cancel_arg));
  if (f->tts_rc) return f->tts_rc;
  *bytes = f->tts_rate == 16000 ? wav(out, 16000, pcm16, 3) :
                                  wav(out, 24000, pcm24, 6);
  if (f->oversize_tts) *bytes = cap + 1;
  return 0;
}

static int play(void *arg, const int16_t *pcm, size_t frames) {
  struct fake *f = arg;
  ++f->play_calls; f->played_frames = frames;
  CHECK(frames <= sizeof(f->played) / sizeof(f->played[0]));
  memcpy(f->played, pcm, frames * sizeof(*pcm));
  return f->play_rc;
}

static int make(struct cloud_speech_orchestrator *o, struct fake *f,
                unsigned char *wav_buf, size_t wav_cap,
                int16_t *pcm, size_t frames) {
  const struct cloud_speech_ops ops = {prompt, asr, tts, play};
  return cloud_speech_init(o, &ops, f, wav_buf, wav_cap, pcm, frames);
}

static int ready(struct cloud_speech_orchestrator *o) {
  int rc = cloud_speech_set_network(o, true, true);
  if (rc) return rc;
  cloud_speech_set_platform_readiness(o,
    CLOUD_SPEECH_DNS_READY | CLOUD_SPEECH_ENTROPY_READY |
    CLOUD_SPEECH_TIME_READY | CLOUD_SPEECH_CA_READY |
    CLOUD_SPEECH_TCP_READY | CLOUD_SPEECH_API_READY);
  return 0;
}

static int test_gate_and_prompt(void) {
  struct fake f = {0}; unsigned char w[128]; int16_t p[16];
  struct cloud_speech_orchestrator o;
  CHECK(make(&o, &f, w, sizeof(w), p, 16) == 0);
  CHECK(!cloud_speech_is_ready(&o));
  CHECK(cloud_speech_set_network(&o, false, true) == CLOUD_SPEECH_EINVAL);
  CHECK(cloud_speech_set_network(&o, true, false) == 0);
  CHECK(f.prompt_calls == 0);
  CHECK(cloud_speech_set_network(&o, true, true) == 0);
  CHECK(f.prompt_calls == 1);
  CHECK(cloud_speech_set_network(&o, true, true) == 0);
  CHECK(f.prompt_calls == 1);
  cloud_speech_set_platform_readiness(&o, 0xffffffffu);
  CHECK(cloud_speech_is_ready(&o));
  CHECK(cloud_speech_set_network(&o, false, false) == 0);
  CHECK(!cloud_speech_is_ready(&o));
  CHECK(cloud_speech_set_network(&o, true, true) == 0);
  CHECK(f.prompt_calls == 2);
  CHECK(!cloud_speech_is_ready(&o)); /* old link's DNS/TLS/API gates are stale */
  cloud_speech_set_platform_readiness(&o, 0xffffffffu);
  CHECK(cloud_speech_is_ready(&o));
  CHECK(cloud_speech_set_network(&o, true, false) == 0);
  CHECK(!cloud_speech_is_ready(&o));
  CHECK(cloud_speech_set_network(&o, true, true) == 0);
  CHECK(!cloud_speech_is_ready(&o));
  return 0;
}

static int test_prompt_retry(void) {
  struct fake f = {.prompt_rc = -1}; unsigned char w[128]; int16_t p[16];
  struct cloud_speech_orchestrator o;
  CHECK(make(&o, &f, w, sizeof(w), p, 16) == 0);
  CHECK(cloud_speech_set_network(&o, true, true) == CLOUD_SPEECH_EPLAY);
  cloud_speech_set_platform_readiness(&o, 0xffffffffu);
  CHECK(!cloud_speech_is_ready(&o));
  f.prompt_rc = 0;
  CHECK(cloud_speech_set_network(&o, true, true) == 0);
  CHECK(f.prompt_calls == 2);
  return 0;
}

static int test_asr_formats(void) {
  const int16_t samples[] = {1, -2, 3};
  struct fake f = {0}; unsigned char w[128], input_wav[64]; int16_t p[16];
  struct cloud_speech_orchestrator o;
  CHECK(make(&o, &f, w, sizeof(w), p, 16) == 0);
  struct cloud_speech_audio a = {CLOUD_SPEECH_AUDIO_PCM16LE,
    (const unsigned char *)samples, sizeof(samples), 16000, 1, 16};
  char text[8]; size_t n;
  CHECK(cloud_speech_transcribe(&o, "runtime-token", &a, text,
                                sizeof(text), &n) == CLOUD_SPEECH_ENOTREADY);
  CHECK(ready(&o) == 0); f.owner = &o;
  CHECK(cloud_speech_transcribe(&o, "runtime-token", &a, text,
                                sizeof(text), &n) == 0);
  CHECK(n == 2 && !strcmp(text, "ok") && f.last_wav_bytes == 50);
  f.drop_link_during_asr = 1;
  CHECK(cloud_speech_transcribe(&o, "runtime-token", &a, text,
                                sizeof(text), &n) == CLOUD_SPEECH_ENOTREADY);
  CHECK(n == 0 && !text[0]);
  f.drop_link_during_asr = 0;
  CHECK(ready(&o) == 0);
  a.sample_rate_hz = 24000;
  CHECK(cloud_speech_transcribe(&o, "runtime-token", &a, text,
                                sizeof(text), &n) == CLOUD_SPEECH_EAUDIO);
  size_t wb = wav(input_wav, 16000, samples, 3);
  a = (struct cloud_speech_audio){CLOUD_SPEECH_AUDIO_WAV_PCM16,
    input_wav, wb, 0, 0, 0};
  CHECK(cloud_speech_transcribe(&o, "runtime-token", &a, text,
                                sizeof(text), &n) == 0);
  input_wav[24] = 0xc0; input_wav[25] = 0x5d; /* 24000 Hz */
  input_wav[28] = 0x80; input_wav[29] = 0xbb; /* 48000 byte/s */
  CHECK(cloud_speech_transcribe(&o, "runtime-token", &a, text,
                                sizeof(text), &n) == CLOUD_SPEECH_EAUDIO);
  return 0;
}

static int test_tts_resample_and_errors(void) {
  struct fake f = {.tts_rate = 24000}; unsigned char w[128]; int16_t p[16];
  struct cloud_speech_orchestrator o;
  CHECK(make(&o, &f, w, sizeof(w), p, 16) == 0);
  CHECK(cloud_speech_synthesize_and_play(&o, "runtime-token", "hello",
                                         "male") == CLOUD_SPEECH_ENOTREADY);
  CHECK(ready(&o) == 0);
  CHECK(cloud_speech_synthesize_and_play(&o, "runtime-token", "hello",
                                         "male") == 0);
  CHECK(f.played_frames == 4);
  CHECK(f.played[0] == 0 && f.played[1] == 450 &&
        f.played[2] == 900 && f.played[3] == 1350);
  f.tts_rate = 16000;
  CHECK(cloud_speech_synthesize_and_play(&o, "runtime-token", "hello",
                                         "male") == 0);
  CHECK(f.played_frames == 3 && f.played[0] == -7 && f.played[2] == 9);
  f.tts_rc = -1;
  CHECK(cloud_speech_synthesize_and_play(&o, "runtime-token", "hello",
                                         "male") == CLOUD_SPEECH_ECLOUD);
  f.tts_rc = 0; f.play_rc = -1;
  CHECK(cloud_speech_synthesize_and_play(&o, "runtime-token", "hello",
                                         "male") == CLOUD_SPEECH_EPLAY);
  f.play_rc = 0; f.oversize_tts = 1;
  CHECK(cloud_speech_synthesize_and_play(&o, "runtime-token", "hello",
                                         "male") == CLOUD_SPEECH_ECLOUD);
  f.oversize_tts = 0;
  o.busy = true;
  CHECK(cloud_speech_synthesize_and_play(&o, "runtime-token", "hello",
                                         "male") == CLOUD_SPEECH_EBUSY);
  return 0;
}

int main(void) {
  int rc = test_gate_and_prompt() || test_prompt_retry() ||
           test_asr_formats() || test_tts_resample_and_errors();
  if (!rc) puts("cloud speech orchestrator: 4 groups passed");
  return rc;
}
