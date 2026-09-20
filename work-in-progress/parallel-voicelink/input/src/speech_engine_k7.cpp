/*
 * speech_engine_k7.cpp
 *
 * sherpa-onnx implementation of include/voicelink/speech_engine.h for K7 + openvela.
 *
 * ASR: sherpa-onnx-streaming-paraformer-bilingual-zh-en (online, INT8)
 * TTS: vits-icefall-zh-aishell3
 *
 * Audio I/O through NuttX PCM devices (ES8388 codec).
 * Model paths configurable via Kconfig.
 */

#include "voicelink/speech_engine.h"

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <math.h>
#include <nuttx/audio/audio.h>
#include <pthread.h>
#include <sherpa-onnx/c-api/c-api.h>
#include <sys/ioctl.h>
#include <syslog.h>
#include <unistd.h>

/* -------------------------------------------------------------------------- */
/* Audio device paths (K7 + ES8388 BSP convention)                            */
/* -------------------------------------------------------------------------- */

#ifndef VOICELINK_AUDIO_OUT_DEV
#define VOICELINK_AUDIO_OUT_DEV "/dev/audio/pcm/outp0"
#endif
#ifndef VOICELINK_AUDIO_INP_DEV
#define VOICELINK_AUDIO_INP_DEV "/dev/audio/pcm/inp0"
#endif

/* -------------------------------------------------------------------------- */
/* Model paths (Kconfig override)                                             */
/* -------------------------------------------------------------------------- */

#ifdef CONFIG_APP_VOICELINK_TTS_MODEL_DIR
#define TTS_DIR CONFIG_APP_VOICELINK_TTS_MODEL_DIR
#else
#define TTS_DIR "/data/voicelink/models/tts"
#endif
#ifdef CONFIG_APP_VOICELINK_ASR_MODEL_DIR
#define ASR_DIR CONFIG_APP_VOICELINK_ASR_MODEL_DIR
#else
#define ASR_DIR "/data/voicelink/models/asr"
#endif

/* -------------------------------------------------------------------------- */
/* Internal state                                                             */
/* -------------------------------------------------------------------------- */

static const SherpaOnnxOfflineTts* g_tts = nullptr;
static const SherpaOnnxOnlineRecognizer* g_recognizer = nullptr;
static pthread_mutex_t g_audio_lock = PTHREAD_MUTEX_INITIALIZER;
static volatile int g_stop_flag = 0;

/* -------------------------------------------------------------------------- */
/* voicelink_speech_init                                                      */
/* -------------------------------------------------------------------------- */

int voicelink_speech_init(void)
{
  /* --- TTS: vits-icefall-zh-aishell3 --- */

  SherpaOnnxOfflineTtsConfig tts_cfg;
  memset(&tts_cfg, 0, sizeof(tts_cfg));

  tts_cfg.model.vits.model      = TTS_DIR "/model.onnx";
  tts_cfg.model.vits.tokens     = TTS_DIR "/tokens.txt";
  tts_cfg.model.vits.lexicon    = TTS_DIR "/lexicon.txt";
  tts_cfg.model.vits.tts_rule_fsts = TTS_DIR "/rule.far";
  tts_cfg.model.vits.length_scale   = 1.0f;
  tts_cfg.model.vits.noise_scale    = 0.667f;
  tts_cfg.model.vits.noise_scale_w  = 0.8f;
  tts_cfg.model.num_threads    = 2;
  tts_cfg.model.debug          = 0;
  tts_cfg.model.provider       = "cpu";
  tts_cfg.max_num_sentences    = 1;
  tts_cfg.sid                  = 0;
  tts_cfg.sampling_rate        = 16000;

  g_tts = SherpaOnnxOfflineTtsCreate(&tts_cfg);
  if (!g_tts) {
    syslog(LOG_ERR, "voicelink: TTS init failed (%s)\n",
           tts_cfg.model.vits.model);
    return -ENOENT;
  }

  /* --- ASR: streaming-paraformer-bilingual-zh-en (INT8) --- */

  SherpaOnnxOnlineRecognizerConfig asr_cfg;
  memset(&asr_cfg, 0, sizeof(asr_cfg));

  asr_cfg.model_config.paraformer.encoder =
      ASR_DIR "/encoder.int8.onnx";
  asr_cfg.model_config.paraformer.decoder =
      ASR_DIR "/decoder.int8.onnx";
  asr_cfg.model_config.tokens    = ASR_DIR "/tokens.txt";
  asr_cfg.model_config.num_threads = 2;
  asr_cfg.model_config.debug     = 0;
  asr_cfg.model_config.provider  = "cpu";
  asr_cfg.decoding_method        = "greedy_search";
  asr_cfg.enable_endpoint        = 1;
  /* Endpoint rules: stop after 2.4 s of silence (non-speech) or 300 ms of
   * silence at the end of an utterance with >= 2 s of preceding speech. */
  asr_cfg.rule1.min_trailing_silence = 2.4f;
  asr_cfg.rule2.min_trailing_silence = 0.8f;
  asr_cfg.rule3.min_utterance_length = 20.0f;

  g_recognizer = SherpaOnnxOnlineRecognizerCreate(&asr_cfg);
  if (!g_recognizer) {
    syslog(LOG_ERR, "voicelink: ASR init failed (%s)\n",
           asr_cfg.model_config.paraformer.encoder);
    SherpaOnnxOfflineTtsDestroy(g_tts);
    g_tts = nullptr;
    return -ENOENT;
  }

  g_stop_flag = 0;
  syslog(LOG_INFO, "voicelink: speech engine ready "
         "(TTS: vits-zh-aishell3, ASR: streaming-paraformer-bilingual)\n");
  return 0;
}

/* -------------------------------------------------------------------------- */
/* voicelink_speech_speak — synthesize and play through ES8388                 */
/* -------------------------------------------------------------------------- */

int voicelink_speech_speak(const char* utf8_text)
{
  if (!utf8_text || !g_tts) return -EINVAL;

  pthread_mutex_lock(&g_audio_lock);
  g_stop_flag = 0;

  const SherpaOnnxGeneratedAudio* audio =
      SherpaOnnxOfflineTtsGenerate(g_tts, utf8_text, 0, 0.8f);
  if (!audio || !audio->samples || audio->n == 0) {
    pthread_mutex_unlock(&g_audio_lock);
    syslog(LOG_ERR, "voicelink: TTS synthesis failed\n");
    return -EIO;
  }

  const int fd = open(VOICELINK_AUDIO_OUT_DEV, O_WRONLY);
  if (fd < 0) {
    SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio);
    pthread_mutex_unlock(&g_audio_lock);
    syslog(LOG_ERR, "voicelink: cannot open " VOICELINK_AUDIO_OUT_DEV "\n");
    return -errno;
  }

  /* Configure PCM output */

  struct audio_caps_s caps;
  caps.ac_len      = sizeof(caps);
  caps.ac_type     = AUDIO_TYPE_OUTPUT;
  caps.ac_channels = 1;
  caps.ac_chmask   = AUDIO_CHANNEL_MONO;
  caps.ac_samprate = audio->sample_rate;
  caps.ac_sampwidth = 16;
  ioctl(fd, AUDIOIOC_CONFIGURE,
        (unsigned long)(uintptr_t)(const void *)&caps);

  /* Write in 40 ms chunks */

  const int16_t* samples = audio->samples;
  const int32_t total = (int32_t)audio->n;
  const int32_t chunk = (int32_t)(audio->sample_rate * 40 / 1000);
  int32_t offset = 0;
  int ret = 0;

  while (offset < total && !g_stop_flag) {
    int32_t n = total - offset;
    if (n > chunk) n = chunk;
    const ssize_t w = write(fd, samples + offset, n * sizeof(int16_t));
    if (w < 0) { ret = -errno; break; }
    offset += (int32_t)(w / sizeof(int16_t));
  }

  close(fd);
  SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio);
  pthread_mutex_unlock(&g_audio_lock);
  return ret;
}

/* -------------------------------------------------------------------------- */
/* voicelink_speech_stop                                                      */
/* -------------------------------------------------------------------------- */

int voicelink_speech_stop(void)
{
  g_stop_flag = 1;
  return 0;
}

/* -------------------------------------------------------------------------- */
/* voicelink_speech_recognize — stream audio to online recognizer              */
/* -------------------------------------------------------------------------- */

int voicelink_speech_recognize(enum voicelink_grammar grammar,
                                char* utf8_text, size_t capacity)
{
  if (!utf8_text || capacity == 0 || !g_recognizer)
    return -EINVAL;

  utf8_text[0] = '\0';

  pthread_mutex_lock(&g_audio_lock);

  const int fd = open(VOICELINK_AUDIO_INP_DEV, O_RDONLY);
  if (fd < 0) {
    pthread_mutex_unlock(&g_audio_lock);
    syslog(LOG_ERR, "voicelink: cannot open " VOICELINK_AUDIO_INP_DEV "\n");
    return -errno;
  }

  /* Configure PCM input: 16 kHz / 16-bit / mono */

  const uint32_t sample_rate = 16000;
  struct audio_caps_s caps;
  caps.ac_len      = sizeof(caps);
  caps.ac_type     = AUDIO_TYPE_INPUT;
  caps.ac_channels = 1;
  caps.ac_chmask   = AUDIO_CHANNEL_MONO;
  caps.ac_samprate = sample_rate;
  caps.ac_sampwidth = 16;
  ioctl(fd, AUDIOIOC_CONFIGURE,
        (unsigned long)(uintptr_t)(const void *)&caps);
  ioctl(fd, AUDIOIOC_START, 0);

  /* Recording limits */

  const int is_wake     = (grammar == VOICELINK_GRAMMAR_WAKE);
  const float max_sec   = is_wake ? 3.0f : 5.0f;
  const float sil_ms    = is_wake ? 600.0f : 800.0f;
  const int32_t max_fr  = (int32_t)(sample_rate * max_sec);
  const int32_t sil_fr  = (int32_t)(sample_rate * sil_ms / 1000);
  const int32_t blk_fr  = (int32_t)(sample_rate * 30 / 1000);  /* 30 ms */

  /* Create a streaming recognizer stream */

  SherpaOnnxOnlineStream* stream =
      SherpaOnnxOnlineRecognizerCreateStream(g_recognizer);
  if (!stream) {
    ioctl(fd, AUDIOIOC_STOP, 0);
    close(fd);
    pthread_mutex_unlock(&g_audio_lock);
    return -EIO;
  }

  int16_t* blk = (int16_t*)malloc((size_t)blk_fr * sizeof(int16_t));
  if (!blk) {
    SherpaOnnxOnlineStreamDestroy(stream);
    ioctl(fd, AUDIOIOC_STOP, 0);
    close(fd);
    pthread_mutex_unlock(&g_audio_lock);
    return -ENOMEM;
  }

  int32_t total = 0;
  int32_t trailing_sil = 0;
  int has_speech = 0;
  int endpoint_detected = 0;

  /* --- Streaming loop: feed 30 ms chunks, check endpoint --- */

  while (total < max_fr && !endpoint_detected) {
    const int32_t want = max_fr - total;
    int32_t count = want < blk_fr ? want : blk_fr;
    const ssize_t n = read(fd, blk, (size_t)count * sizeof(int16_t));
    if (n <= 0) break;
    const int32_t frames = (int32_t)(n / sizeof(int16_t));
    total += frames;

    /* Feed chunk to streaming recognizer */

    SherpaOnnxOnlineRecognizerAcceptWaveform_i16(
        stream, sample_rate, blk, frames);

    /* Check for endpoint (silence-based endpointing built into sherpa-onnx) */

    if (SherpaOnnxOnlineRecognizerIsEndpoint(g_recognizer, stream)) {
      if (has_speech) endpoint_detected = 1;
    }

    /* Simple RMS VAD for timeout detection */

    int64_t sum_sq = 0;
    for (int32_t i = 0; i < frames; ++i)
      sum_sq += (int64_t)blk[i] * blk[i];
    const float rms = sqrtf((float)(sum_sq / frames));

    if (rms > 300.0f) {
      has_speech = 1;
      trailing_sil = 0;
    } else {
      trailing_sil += frames;
      if (has_speech && trailing_sil >= sil_fr) break;
    }
    if (!has_speech && total > (int32_t)(sample_rate * 1.5f)) break;
  }

  ioctl(fd, AUDIOIOC_STOP, 0);
  close(fd);
  free(blk);

  /* No speech detected */

  if (!has_speech || total < (int32_t)(sample_rate * 0.1f)) {
    SherpaOnnxOnlineStreamDestroy(stream);
    pthread_mutex_unlock(&g_audio_lock);
    return VOICELINK_SPEECH_TIMEOUT;
  }

  /* Signal end of input and get final result */

  SherpaOnnxOnlineRecognizerInputFinished(stream);
  SherpaOnnxOnlineRecognizerDecode(g_recognizer, stream);

  const SherpaOnnxOnlineRecognizerResult* result =
      SherpaOnnxOnlineRecognizerGetResult(g_recognizer, stream);

  int ret;
  if (result && result->text && result->text[0] != '\0') {
    strncpy(utf8_text, result->text, capacity - 1);
    utf8_text[capacity - 1] = '\0';
    ret = VOICELINK_SPEECH_OK;
  } else {
    ret = VOICELINK_SPEECH_RETRY;
  }

  if (result) SherpaOnnxDestroyOnlineRecognizerResult(result);
  SherpaOnnxOnlineStreamDestroy(stream);
  pthread_mutex_unlock(&g_audio_lock);
  return ret;
}
