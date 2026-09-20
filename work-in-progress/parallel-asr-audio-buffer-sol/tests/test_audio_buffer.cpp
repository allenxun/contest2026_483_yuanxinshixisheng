#include "voicelink/asr_runtime.h"
#include "sherpa-onnx/c-api/c-api.h"

#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace std::chrono_literals;

#define CHECK(x) do { if (!(x)) throw std::runtime_error(#x); } while (0)

struct SherpaOnnxOnlineRecognizer {};
struct SherpaOnnxOnlineStream { int ready = 1; };

static std::atomic<int> recognizers{0};
static std::atomic<int> streams{0};
static std::atomic<int> results{0};
static std::atomic<int> decode_delay_ms{0};
static std::atomic<int> ready_rounds{1};
static std::atomic<int> capture_calls{0};
static std::atomic<int> accepts{0};
static std::atomic<int> active_decodes{0};
static std::atomic<bool> decode_entered{false};
static std::vector<float> captured_samples;
static int captured_rate = 0;
static const char *result_text = "recognized";

extern "C" int k7_tls_selftest(void) { return 0; }

extern "C" int k7sound_copy_mono(float *out, unsigned capacity,
                                  unsigned *frames) {
  ++capture_calls;
  if (capacity < 3) return -ENOSPC;
  out[0] = 0.75f; out[1] = -0.25f; out[2] = 0.5f;
  *frames = 3;
  return 0;
}

extern "C" const SherpaOnnxOnlineRecognizer *
SherpaOnnxCreateOnlineRecognizer(const SherpaOnnxOnlineRecognizerConfig *) {
  ++recognizers;
  return new SherpaOnnxOnlineRecognizer;
}
extern "C" void SherpaOnnxDestroyOnlineRecognizer(
    const SherpaOnnxOnlineRecognizer *value) {
  delete value; --recognizers;
}
extern "C" const SherpaOnnxOnlineStream *SherpaOnnxCreateOnlineStream(
    const SherpaOnnxOnlineRecognizer *) {
  ++streams;
  auto *value = new SherpaOnnxOnlineStream;
  value->ready = ready_rounds.load();
  return value;
}
extern "C" void SherpaOnnxDestroyOnlineStream(
    const SherpaOnnxOnlineStream *value) {
  delete value; --streams;
}
extern "C" int SherpaOnnxIsOnlineStreamReady(
    const SherpaOnnxOnlineRecognizer *, const SherpaOnnxOnlineStream *value) {
  return value->ready > 0;
}
extern "C" void SherpaOnnxDecodeOnlineStream(
    const SherpaOnnxOnlineRecognizer *, const SherpaOnnxOnlineStream *value) {
  ++active_decodes;
  decode_entered.store(true);
  std::this_thread::sleep_for(std::chrono::milliseconds(decode_delay_ms.load()));
  --const_cast<SherpaOnnxOnlineStream *>(value)->ready;
  --active_decodes;
}
extern "C" void SherpaOnnxOnlineStreamAcceptWaveform(
    const SherpaOnnxOnlineStream *, int rate, const float *samples, int count) {
  ++accepts;
  captured_rate = rate;
  if (accepts.load() == 1) captured_samples.assign(samples, samples + count);
}
extern "C" void SherpaOnnxOnlineStreamInputFinished(
    const SherpaOnnxOnlineStream *) {}
extern "C" const SherpaOnnxOnlineRecognizerResult *
SherpaOnnxGetOnlineStreamResult(const SherpaOnnxOnlineRecognizer *,
                               const SherpaOnnxOnlineStream *) {
  ++results;
  auto *value = new SherpaOnnxOnlineRecognizerResult;
  value->text = result_text;
  return value;
}
extern "C" void SherpaOnnxDestroyOnlineRecognizerResult(
    const SherpaOnnxOnlineRecognizerResult *value) {
  delete value; --results;
}

static uint64_t now_ms() {
  return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count());
}

static k7_asr_audio_request request(const float *samples, unsigned frames) {
  return {samples, frames, 16000, 0, nullptr, nullptr};
}

static void reset_fake() {
  CHECK(recognizers == 0 && streams == 0 && results == 0);
  decode_delay_ms = 0;
  ready_rounds = 1;
  capture_calls = 0;
  accepts = 0;
  active_decodes = 0;
  decode_entered = false;
  captured_samples.clear();
  captured_rate = 0;
  result_text = "recognized";
}

static void test_direct_samples_and_validation() {
  reset_fake();
  float samples[] = {0.125f, -0.5f, 0.9f};
  char out[32] = "dirty";
  auto req = request(samples, 3);
  CHECK(k7_asr_audio_text(&req, out, sizeof(out)) == 0);
  CHECK(std::strcmp(out, "recognized") == 0);
  CHECK(capture_calls == 0);
  CHECK(captured_rate == 16000 && captured_samples.size() == 3);
  CHECK(captured_samples[0] == samples[0] && captured_samples[2] == samples[2]);
  CHECK(recognizers == 0 && streams == 0 && results == 0);

  req.frames = 0; std::strcpy(out, "dirty");
  CHECK(k7_asr_audio_text(&req, out, sizeof(out)) == -ENODATA && out[0] == 0);
  req.frames = 48001;
  CHECK(k7_asr_audio_text(&req, out, sizeof(out)) == -EOVERFLOW && out[0] == 0);
  req.frames = 3; req.sample_rate_hz = 8000;
  CHECK(k7_asr_audio_text(&req, out, sizeof(out)) == -EINVAL && out[0] == 0);
  req.sample_rate_hz = 16000; req.samples = nullptr;
  CHECK(k7_asr_audio_text(&req, out, sizeof(out)) == -ENODATA && out[0] == 0);
  CHECK(k7_asr_audio_text(nullptr, out, sizeof(out)) == -EINVAL && out[0] == 0);
}

static void test_enospc_and_raii() {
  reset_fake();
  float samples[] = {0.1f};
  auto req = request(samples, 1);
  char out[4] = "xxx";
  CHECK(k7_asr_audio_text(&req, out, sizeof(out)) == -ENOSPC);
  CHECK(out[0] == 0);
  CHECK(recognizers == 0 && streams == 0 && results == 0);

  reset_fake();
  ready_rounds = 129;
  char large[32] = "dirty";
  CHECK(k7_asr_audio_text(&req, large, sizeof(large)) == -ETIMEDOUT);
  CHECK(large[0] == 0);
  CHECK(recognizers == 0 && streams == 0 && results == 0);
}

static int cancelled(void *ctx) {
  return static_cast<std::atomic<bool> *>(ctx)->load() ? 1 : 0;
}

static void test_cancel_deadline_and_raii() {
  reset_fake();
  float samples[] = {0.1f};
  char out[32];
  std::atomic<bool> cancel{true};
  auto req = request(samples, 1);
  req.cancel_requested = cancelled; req.cancel_ctx = &cancel;
  CHECK(k7_asr_audio_text(&req, out, sizeof(out)) == -ECANCELED);
  CHECK(recognizers == 0 && streams == 0 && results == 0);

  cancel = false;
  ready_rounds = 100;
  decode_delay_ms = 2;
  req.deadline_ms = now_ms() + 12;
  CHECK(k7_asr_audio_text(&req, out, sizeof(out)) == -ETIMEDOUT);
  CHECK(out[0] == 0);
  CHECK(recognizers == 0 && streams == 0 && results == 0);

  reset_fake();
  ready_rounds = 100;
  decode_delay_ms = 1;
  req.deadline_ms = 0;
  cancel = false;
  std::thread trigger([&] {
    while (!decode_entered.load()) std::this_thread::yield();
    cancel = true;
  });
  CHECK(k7_asr_audio_text(&req, out, sizeof(out)) == -ECANCELED);
  trigger.join();
  CHECK(recognizers == 0 && streams == 0 && results == 0);
}

static void test_concurrent_busy_and_gate_release() {
  reset_fake();
  ready_rounds = 1;
  decode_delay_ms = 80;
  float samples[] = {0.2f};
  auto req = request(samples, 1);
  char first[32];
  int first_error = -1;
  std::thread owner([&] { first_error = k7_asr_audio_text(&req, first, sizeof(first)); });
  while (!decode_entered.load()) std::this_thread::yield();
  char second[32] = "dirty";
  CHECK(k7_asr_audio_text(&req, second, sizeof(second)) == -EBUSY);
  CHECK(second[0] == 0);
  owner.join();
  CHECK(first_error == 0);
  decode_delay_ms = 0;
  decode_entered = false;
  CHECK(k7_asr_audio_text(&req, second, sizeof(second)) == 0);
  CHECK(recognizers == 0 && streams == 0 && results == 0);
}

static void test_microphone_wrapper_captures_once() {
  reset_fake();
  char out[32];
  CHECK(k7_asr_microphone_text(out, sizeof(out)) == 0);
  CHECK(capture_calls == 1);
  CHECK(captured_samples.size() == 3 && captured_samples[0] == 0.75f);
  CHECK(recognizers == 0 && streams == 0 && results == 0);
}

int main() {
  try {
    test_direct_samples_and_validation();
    test_enospc_and_raii();
    test_cancel_deadline_and_raii();
    test_concurrent_busy_and_gate_release();
    test_microphone_wrapper_captures_once();
    std::cout << "direct_owned_samples_no_recapture=PASS\n"
                 "invalid_frames_rate_and_limit=PASS\n"
                 "enospc_decode_budget_raii=PASS\n"
                 "cooperative_cancel_deadline_raii=PASS\n"
                 "concurrent_busy_gate_release=PASS\n"
                 "microphone_wrapper_single_capture=PASS\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "FAIL " << error.what() << '\n';
    return 1;
  }
}
