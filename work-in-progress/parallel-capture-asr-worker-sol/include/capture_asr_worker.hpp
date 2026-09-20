#ifndef VELAVISION_CAPTURE_ASR_WORKER_HPP
#define VELAVISION_CAPTURE_ASR_WORKER_HPP

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace capture_asr {

enum class SubmitStatus {
  Accepted,
  Busy,
  Stale,
  CaptureFailed,
  Cancelled,
  Stopped
};
enum class ResultStatus { Completed, Cancelled, TimedOut, Failed };

struct SubmitResult {
  SubmitStatus status = SubmitStatus::Stopped;
  int error = 0;
};

struct Result {
  std::uint64_t generation = 0;
  ResultStatus status = ResultStatus::Failed;
  int error = 0;
  std::string text;
};

class CaptureSource {
 public:
  virtual ~CaptureSource() = default;
  virtual int copyMono(float *destination, unsigned capacity,
                       unsigned *frames) = 0;
};

class Cancellation {
 public:
  bool requested() const noexcept;
  bool deadlineReached() const noexcept;

 private:
  friend class Worker;
  Cancellation(const std::atomic<bool> &cancelled,
               std::chrono::steady_clock::time_point deadline);
  const std::atomic<bool> &cancelled_;
  std::chrono::steady_clock::time_point deadline_;
};

class Backend {
 public:
  virtual ~Backend() = default;
  // The samples remain valid only for this call. Implementations must poll the
  // cancellation/deadline token during long model setup and decode loops.
  virtual int recognize(const float *samples, unsigned frames,
                        const Cancellation &cancellation,
                        std::string &text) = 0;
};

class Worker {
 public:
  explicit Worker(Backend &backend, unsigned max_frames = 48000);
  ~Worker();
  Worker(const Worker &) = delete;
  Worker &operator=(const Worker &) = delete;

  // Called after capture completion. It only reserves/copies an owned snapshot
  // and queues work; model execution happens exclusively on the worker thread.
  SubmitResult captureCompleted(std::uint64_t generation,
                                std::chrono::milliseconds timeout,
                                CaptureSource &source);
  void cancelThrough(std::uint64_t generation);
  bool poll(Result &result);
  std::size_t droppedResults() const;

 private:
  enum class SlotState { Free, Filling, Queued, Running };
  struct Slot {
    explicit Slot(unsigned capacity) : samples(capacity) {}
    std::vector<float> samples;
    unsigned frames = 0;
    std::uint64_t generation = 0;
    std::chrono::steady_clock::time_point deadline{};
    SlotState state = SlotState::Free;
    std::atomic<bool> cancelled{false};
  };

  void run();
  void pushResultLocked(Result result);
  void releaseLocked(Slot &slot);

  Backend &backend_;
  const unsigned max_frames_;
  mutable std::mutex mutex_;
  std::condition_variable wake_;
  Slot slots_[2];                 // one running plus one pending snapshot
  std::deque<Result> results_;   // bounded terminal-event queue
  std::thread thread_;
  std::uint64_t newest_generation_ = 0;
  std::uint64_t cancelled_through_ = 0;
  std::size_t dropped_results_ = 0;
  bool stopping_ = false;
};

class K7SoundCaptureSource final : public CaptureSource {
 public:
  int copyMono(float *destination, unsigned capacity,
               unsigned *frames) override;
};

// Diagnostic compatibility only. The legacy function ignores the supplied
// snapshot and fetches "the last completed capture" again when the worker runs.
class LegacyMicrophoneTextBackend final : public Backend {
 public:
  int recognize(const float *samples, unsigned frames,
                const Cancellation &cancellation,
                std::string &text) override;
};

}  // namespace capture_asr

#endif
