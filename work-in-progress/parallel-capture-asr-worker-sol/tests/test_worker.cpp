#include "capture_asr_worker.hpp"

#include <atomic>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace std::chrono_literals;
using capture_asr::Backend;
using capture_asr::Cancellation;
using capture_asr::CaptureSource;
using capture_asr::Result;
using capture_asr::ResultStatus;
using capture_asr::SubmitStatus;
using capture_asr::Worker;

#define CHECK(value) do { if (!(value)) throw std::runtime_error(#value); } while (0)

static std::vector<float> legacy_capture{0.25f, -0.5f};
static std::string legacy_text = "legacy";

extern "C" int k7sound_copy_mono(float *out, unsigned capacity,
                                  unsigned *frames) {
  if (capacity < legacy_capture.size()) return -ENOSPC;
  std::memcpy(out, legacy_capture.data(), legacy_capture.size() * sizeof(float));
  *frames = static_cast<unsigned>(legacy_capture.size());
  return 0;
}

extern "C" int k7_asr_microphone_text(char *out, std::size_t capacity) {
  if (capacity <= legacy_text.size()) return -ENOSPC;
  std::memcpy(out, legacy_text.c_str(), legacy_text.size() + 1);
  return 0;
}

class FakeCapture final : public CaptureSource {
 public:
  explicit FakeCapture(std::vector<float> values) : values_(std::move(values)) {}
  int copyMono(float *destination, unsigned capacity, unsigned *frames) override {
    if (capacity < values_.size()) return -ENOSPC;
    std::memcpy(destination, values_.data(), values_.size() * sizeof(float));
    *frames = static_cast<unsigned>(values_.size());
    return error_;
  }
  std::vector<float> values_;
  int error_ = 0;
};

class FakeBackend final : public Backend {
 public:
  int recognize(const float *samples, unsigned frames,
                const Cancellation &cancel, std::string &text) override {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      entered_ = true;
      first_sample_ = frames ? samples[0] : 0;
      thread_id_ = std::this_thread::get_id();
    }
    condition_.notify_all();
    if (throw_) throw std::runtime_error("fake backend exception");
    while (hold_.load() && !cancel.requested() && !cancel.deadlineReached())
      std::this_thread::sleep_for(1ms);
    if (cancel.requested()) return -ECANCELED;
    if (cancel.deadlineReached()) return -ETIMEDOUT;
    text = "sample=" + std::to_string(first_sample_);
    return error_;
  }
  void waitEntered() {
    std::unique_lock<std::mutex> lock(mutex_);
    CHECK(condition_.wait_for(lock, 5s, [&] { return entered_; }));
    entered_ = false;
  }
  std::atomic<bool> hold_{false};
  int error_ = 0;
  bool throw_ = false;
  float first_sample_ = 0;
  std::thread::id thread_id_{};
 private:
  std::mutex mutex_;
  std::condition_variable condition_;
  bool entered_ = false;
};

static Result waitResult(Worker &worker, std::uint64_t generation) {
  auto deadline = std::chrono::steady_clock::now() + 2s;
  while (std::chrono::steady_clock::now() < deadline) {
    Result result;
    if (worker.poll(result) && result.generation == generation) return result;
    std::this_thread::sleep_for(1ms);
  }
  throw std::runtime_error("result timeout");
}

static void test_snapshot_ownership_and_nonblocking_submit() {
  FakeBackend backend;
  backend.hold_ = true;
  Worker worker(backend, 8);
  FakeCapture capture({0.25f, 0.5f});
  const auto capture_thread = std::this_thread::get_id();
  auto started = std::chrono::steady_clock::now();
  CHECK(worker.captureCompleted(1, 1s, capture).status == SubmitStatus::Accepted);
  CHECK(std::chrono::steady_clock::now() - started < 100ms);
  capture.values_[0] = 0.9f;
  backend.waitEntered();
  CHECK(backend.thread_id_ != capture_thread);
  CHECK(backend.first_sample_ == 0.25f);
  backend.hold_ = false;
  Result result = waitResult(worker, 1);
  CHECK(result.status == ResultStatus::Completed);
}

static void test_single_pending_slot_and_supersession() {
  FakeBackend backend;
  backend.hold_ = true;
  Worker worker(backend, 8);
  FakeCapture one({1.0f}), two({2.0f}), three({3.0f});
  CHECK(worker.captureCompleted(10, 1s, one).status == SubmitStatus::Accepted);
  backend.waitEntered();
  CHECK(worker.captureCompleted(11, 1s, two).status == SubmitStatus::Accepted);
  CHECK(worker.captureCompleted(12, 1s, three).status == SubmitStatus::Busy);
  Result old = waitResult(worker, 10);
  CHECK(old.status == ResultStatus::Cancelled);
  backend.hold_ = false;
  Result current = waitResult(worker, 11);
  CHECK(current.status == ResultStatus::Completed);
  CHECK(worker.captureCompleted(11, 1s, two).status == SubmitStatus::Stale);
}

static void test_cancel_and_timeout() {
  FakeBackend backend;
  backend.hold_ = true;
  Worker worker(backend, 8);
  FakeCapture capture({4.0f});
  CHECK(worker.captureCompleted(20, 1s, capture).status == SubmitStatus::Accepted);
  backend.waitEntered();
  worker.cancelThrough(20);
  CHECK(waitResult(worker, 20).status == ResultStatus::Cancelled);
  CHECK(worker.captureCompleted(21, 25ms, capture).status == SubmitStatus::Accepted);
  backend.waitEntered();
  CHECK(waitResult(worker, 21).status == ResultStatus::TimedOut);
}

static void test_capture_failure_and_adapters() {
  FakeBackend backend;
  Worker worker(backend, 8);
  FakeCapture failed({1.0f});
  failed.error_ = -EIO;
  auto submission = worker.captureCompleted(30, 1s, failed);
  CHECK(submission.status == SubmitStatus::CaptureFailed);
  CHECK(submission.error == -EIO);

  capture_asr::K7SoundCaptureSource source;
  float samples[4]{};
  unsigned frames = 0;
  CHECK(source.copyMono(samples, 4, &frames) == 0);
  CHECK(frames == 2 && samples[0] == 0.25f && samples[1] == -0.5f);

  capture_asr::LegacyMicrophoneTextBackend legacy;
  std::atomic<bool> cancelled{false};
  // Exercise the compatibility adapter through a worker because Cancellation
  // construction is intentionally private.
  Worker legacy_worker(legacy, 8);
  FakeCapture snapshot({99.0f});
  CHECK(legacy_worker.captureCompleted(31, 1s, snapshot).status == SubmitStatus::Accepted);
  Result result = waitResult(legacy_worker, 31);
  CHECK(result.status == ResultStatus::Completed && result.text == "legacy");
}

static void test_backend_exception_does_not_kill_worker() {
  FakeBackend backend;
  backend.throw_ = true;
  Worker worker(backend, 8);
  FakeCapture capture({7.0f});
  CHECK(worker.captureCompleted(40, 1s, capture).status == SubmitStatus::Accepted);
  CHECK(waitResult(worker, 40).status == ResultStatus::Failed);
  backend.throw_ = false;
  CHECK(worker.captureCompleted(41, 1s, capture).status == SubmitStatus::Accepted);
  CHECK(waitResult(worker, 41).status == ResultStatus::Completed);
}

int main() {
  try {
    test_snapshot_ownership_and_nonblocking_submit();
    test_single_pending_slot_and_supersession();
    test_cancel_and_timeout();
    test_capture_failure_and_adapters();
    test_backend_exception_does_not_kill_worker();
    std::cout << "snapshot_ownership_nonblocking=PASS\n"
                 "single_pending_busy_supersession=PASS\n"
                 "cooperative_cancel_timeout=PASS\n"
                 "k7_contract_adapters=PASS\n"
                 "backend_exception_containment=PASS\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "FAIL " << error.what() << '\n';
    return 1;
  }
}
