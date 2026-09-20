#include "voicelink/asr_runtime.h"
#include "sherpa-onnx/c-api/c-api.h"

#include <atomic>
#include <cerrno>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>

struct SherpaOnnxOnlineRecognizer {};
struct SherpaOnnxOnlineStream {};

namespace {
std::atomic<unsigned> accepted_samples{0};
std::atomic<int> capture_error{0};
std::atomic<unsigned> capture_frames{4};
std::atomic<int> result_destroyed{0};
std::atomic<int> stream_destroyed{0};
std::atomic<int> recognizer_destroyed{0};
std::mutex block_mutex;
std::condition_variable block_cv;
bool block_create = false;
bool create_entered = false;
const char *result_text = "ASR_PRIVATE_TEST_TOKEN";

void reset_counts() {
  result_destroyed = 0;
  stream_destroyed = 0;
  recognizer_destroyed = 0;
}

void require(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", message);
    std::exit(1);
  }
}
}

extern "C" int k7_tls_selftest(void) { return 0; }

extern "C" int k7sound_copy_mono(float *out, unsigned capacity,
                                   unsigned *frames) {
  const int error = capture_error.load();
  if (error) return error;
  const unsigned requested = capture_frames.load();
  for (unsigned i = 0; i < capacity && i < requested; ++i) out[i] = 0.0f;
  *frames = requested;
  return 0;
}

extern "C" const SherpaOnnxOnlineRecognizer *SherpaOnnxCreateOnlineRecognizer(
    const SherpaOnnxOnlineRecognizerConfig *) {
  std::unique_lock<std::mutex> lock(block_mutex);
  if (block_create) {
    create_entered = true;
    block_cv.notify_all();
    block_cv.wait(lock, [] { return !block_create; });
  }
  return new SherpaOnnxOnlineRecognizer;
}

extern "C" void SherpaOnnxDestroyOnlineRecognizer(
    const SherpaOnnxOnlineRecognizer *p) {
  ++recognizer_destroyed;
  delete p;
}

extern "C" const SherpaOnnxOnlineStream *SherpaOnnxCreateOnlineStream(
    const SherpaOnnxOnlineRecognizer *) { return new SherpaOnnxOnlineStream; }

extern "C" void SherpaOnnxDestroyOnlineStream(const SherpaOnnxOnlineStream *p) {
  ++stream_destroyed;
  delete p;
}

extern "C" void SherpaOnnxOnlineStreamAcceptWaveform(
    const SherpaOnnxOnlineStream *, int32_t, const float *, int32_t count) { accepted_samples += unsigned(count); }
extern "C" void SherpaOnnxOnlineStreamInputFinished(
    const SherpaOnnxOnlineStream *) {}
extern "C" int32_t SherpaOnnxIsOnlineStreamReady(
    const SherpaOnnxOnlineRecognizer *, const SherpaOnnxOnlineStream *) { return 0; }
extern "C" void SherpaOnnxDecodeOnlineStream(
    const SherpaOnnxOnlineRecognizer *, const SherpaOnnxOnlineStream *) {}

extern "C" const SherpaOnnxOnlineRecognizerResult *SherpaOnnxGetOnlineStreamResult(
    const SherpaOnnxOnlineRecognizer *, const SherpaOnnxOnlineStream *) {
  auto *result = static_cast<SherpaOnnxOnlineRecognizerResult *>(
      std::calloc(1, sizeof(SherpaOnnxOnlineRecognizerResult)));
  result->text = result_text;
  return result;
}

extern "C" void SherpaOnnxDestroyOnlineRecognizerResult(
    const SherpaOnnxOnlineRecognizerResult *result) {
  ++result_destroyed;
  std::free(const_cast<SherpaOnnxOnlineRecognizerResult *>(result));
}

int main(int argc, char **argv) {
  if (argc == 2 && std::string(argv[1]) == "fixture") {
    const int rc = k7_asr_model_session_probe();
    require(rc == 0, "fixed fixture accepted beyond capture limit");
    require(accepted_samples == 160850 + 4800, "entire fixture plus tail fed");
    require(result_destroyed == 1 && stream_destroyed == 1 && recognizer_destroyed == 1, "fixture cleanup");
    puts("PASS fixed fixture 160850 frames, exact feed and cleanup"); return 0;
  }
  const bool baseline = argc == 2 && std::string(argv[1]) == "baseline";
  char text[64];

  reset_counts();
  capture_error = 0;
  capture_frames = 4;
  int rc = k7_asr_microphone_text(text, sizeof(text));
  require(rc == 0 && std::strcmp(text, result_text) == 0, "success copy");
  require(result_destroyed == 1 && stream_destroyed == 1 && recognizer_destroyed == 1,
          "success cleanup");

  reset_counts();
  char small[5] = "junk";
  rc = k7_asr_microphone_text(small, sizeof(small));
  require(rc == -ENOSPC && small[0] == '\0', "bounded output rejection");
  require(result_destroyed == 1 && stream_destroyed == 1 && recognizer_destroyed == 1,
          "oversize cleanup");

  capture_error = -EBUSY;
  std::strcpy(text, "junk");
  rc = k7_asr_microphone_text(text, sizeof(text));
  if (baseline) {
    require(rc == -EIO, "baseline reproduces collapsed capture error");
    std::puts("OBSERVED baseline_capture_busy=-EIO expected_preserved=-EBUSY");
  } else {
    require(rc == -EBUSY && text[0] == '\0', "capture error propagation");
  }

  if (!baseline) {
    capture_error = 0;
    capture_frames = 48001;
    rc = k7_asr_microphone_text(text, sizeof(text));
    require(rc == -EOVERFLOW && text[0] == '\0', "capture frame bound");

    capture_frames = 4;
    {
      std::unique_lock<std::mutex> lock(block_mutex);
      block_create = true;
      create_entered = false;
    }
    std::atomic<int> first_rc{999};
    std::thread first([&] {
      char first_text[64];
      first_rc = k7_asr_microphone_text(first_text, sizeof(first_text));
    });
    {
      std::unique_lock<std::mutex> lock(block_mutex);
      block_cv.wait(lock, [] { return create_entered; });
    }
    char second_text[64] = "junk";
    const int second_rc = k7_asr_microphone_text(second_text, sizeof(second_text));
    require(second_rc == -EBUSY && second_text[0] == '\0', "concurrent gate");
    {
      std::lock_guard<std::mutex> lock(block_mutex);
      block_create = false;
    }
    block_cv.notify_all();
    first.join();
    require(first_rc == 0, "gate owner completes");
  }

  std::puts(baseline ? "PASS baseline_reproduction" : "PASS candidate_host_fake");
  return 0;
}
