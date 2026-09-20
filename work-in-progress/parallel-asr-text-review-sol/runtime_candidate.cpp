#include "voicelink/asr_runtime.h"
#include "sherpa-onnx/c-api/c-api.h"
#include "test_assets.h"

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <exception>
#include <memory>
#include <pthread.h>
#include <stdexcept>
#include <unistd.h>

extern "C" int k7_tls_selftest(void);
extern "C" int k7sound_copy_mono(float *, unsigned, unsigned *);

namespace {

constexpr unsigned kMaxMicrophoneFrames = 48000;

struct Handles {
  const SherpaOnnxOnlineRecognizer *recognizer = nullptr;
  const SherpaOnnxOnlineStream *stream = nullptr;
  const SherpaOnnxOnlineRecognizerResult *result = nullptr;

  ~Handles() {
    if (result) SherpaOnnxDestroyOnlineRecognizerResult(result);
    if (stream) SherpaOnnxDestroyOnlineStream(stream);
    if (recognizer) SherpaOnnxDestroyOnlineRecognizer(recognizer);
  }
};

double seconds() {
  timespec time{};
  if (clock_gettime(CLOCK_MONOTONIC, &time)) throw std::runtime_error("clock");
  return time.tv_sec + time.tv_nsec / 1e9;
}

pthread_mutex_t asr_gate = PTHREAD_MUTEX_INITIALIZER;

int copy_text(const char *source, char *destination, size_t capacity) {
  if (!destination || !capacity) return -EINVAL;
  destination[0] = '\0';
  if (!source || !source[0]) return -ENODATA;
  size_t length = 0;
  while (length < capacity && source[length]) ++length;
  if (length == capacity) return -ENOSPC;
  std::memcpy(destination, source, length + 1);
  return 0;
}

int recognize(bool microphone, char *utf8_text, size_t capacity) {
  if (utf8_text && capacity) utf8_text[0] = '\0';
  if ((utf8_text == nullptr) != (capacity == 0)) return -EINVAL;
  const int lock_error = pthread_mutex_trylock(&asr_gate);
  if (lock_error) {
    if (lock_error == EBUSY) std::puts("ASR_INFER busy");
    else std::printf("ASR_INFER gate_error=%d\n", lock_error);
    return -lock_error;
  }
  struct Gate {
    ~Gate() { pthread_mutex_unlock(&asr_gate); }
  } gate;

  try {
    const double start = seconds();
    Handles handles;
    if (k7_tls_selftest()) throw std::runtime_error("TLS isolation check");
    std::unique_ptr<float[]> recorded;
    unsigned frames = test_frames;
    if (microphone) {
      recorded.reset(new float[kMaxMicrophoneFrames]);
      const int capture_error =
          k7sound_copy_mono(recorded.get(), kMaxMicrophoneFrames, &frames);
      if (capture_error) return capture_error;
      if (!frames || frames > kMaxMicrophoneFrames) return -EOVERFLOW;
      std::printf("ASR_MIC frames=%u rate=16000 channel=left\n", frames);
    }

    SherpaOnnxOnlineRecognizerConfig config{};
    config.feat_config.sample_rate = 16000;
    config.feat_config.feature_dim = 80;
    config.model_config.paraformer.encoder = "k7ram:encoder";
    config.model_config.paraformer.decoder = "k7ram:decoder";
    config.model_config.tokens_buf = reinterpret_cast<const char *>(test_tokens);
    config.model_config.tokens_buf_size = sizeof(test_tokens) - 1;
    config.model_config.num_threads = 1;
    config.model_config.provider = "cpu";
    config.model_config.model_type = "paraformer";
    config.decoding_method = "greedy_search";

    std::puts("ASR_INFER BEGIN recognizer");
    std::fflush(stdout);
    handles.recognizer = SherpaOnnxCreateOnlineRecognizer(&config);
    if (!handles.recognizer) throw std::runtime_error("recognizer creation");
    handles.stream = SherpaOnnxCreateOnlineStream(handles.recognizer);
    if (!handles.stream) throw std::runtime_error("stream creation");

    unsigned steps = 0;
    auto decode = [&]() {
      while (SherpaOnnxIsOnlineStreamReady(handles.recognizer, handles.stream)) {
        if (++steps > 128 || seconds() - start > 180)
          throw std::runtime_error("decode budget");
        SherpaOnnxDecodeOnlineStream(handles.recognizer, handles.stream);
        std::printf("ASR_INFER chunk=%u elapsed=%.3f\n", steps, seconds() - start);
        std::fflush(stdout);
        usleep(1000);
      }
    };

    float samples[1600];
    for (unsigned offset = 0; offset < frames;) {
      unsigned count = frames - offset;
      if (count > 1600) count = 1600;
      for (unsigned index = 0; index < count; ++index) {
        if (microphone) {
          samples[index] = recorded[offset + index];
          continue;
        }
        const unsigned byte = 2 * (offset + index);
        int value = test_pcm[byte] | (unsigned(test_pcm[byte + 1]) << 8);
        if (value >= 32768) value -= 65536;
        samples[index] = float(value) / 32768.0f;
      }
      SherpaOnnxOnlineStreamAcceptWaveform(handles.stream, 16000, samples, count);
      offset += count;
      decode();
    }

    std::memset(samples, 0, sizeof(samples));
    for (unsigned index = 0; index < 3; ++index)
      SherpaOnnxOnlineStreamAcceptWaveform(handles.stream, 16000, samples, 1600);
    SherpaOnnxOnlineStreamInputFinished(handles.stream);
    decode();
    handles.result = SherpaOnnxGetOnlineStreamResult(handles.recognizer, handles.stream);
    if (!handles.result || !handles.result->text || !handles.result->text[0])
      throw std::runtime_error("empty recognition result");

    const int copied = utf8_text ? copy_text(handles.result->text, utf8_text, capacity) : 0;
    if (copied) return copied;
    std::printf("ASR_INFER RESULT seconds=%.3f text=%s\n",
                seconds() - start, handles.result->text);
    return 0;
  } catch (const std::bad_alloc &) {
    std::puts("ASR_INFER FAIL allocation");
    return -ENOMEM;
  } catch (const std::exception &error) {
    std::printf("ASR_INFER FAIL %s\n", error.what());
    return -EIO;
  } catch (...) {
    std::puts("ASR_INFER FAIL unknown exception");
    return -EIO;
  }
}

}  // namespace

extern "C" int k7_asr_model_session_probe(void) {
  return recognize(false, nullptr, 0);
}

extern "C" int k7_asr_microphone_probe(void) {
  return recognize(true, nullptr, 0);
}

extern "C" int k7_asr_microphone_text(char *utf8_text, size_t capacity) {
  return recognize(true, utf8_text, capacity);
}
