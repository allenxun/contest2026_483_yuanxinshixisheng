#include "capture_asr_worker.hpp"

#include <cerrno>
#include <cstring>
#include <utility>

extern "C" int k7sound_copy_mono(float *, unsigned, unsigned *);
extern "C" int k7_asr_microphone_text(char *, std::size_t);

namespace capture_asr {
namespace {
constexpr std::size_t kResultCapacity = 8;
constexpr std::size_t kLegacyTextCapacity = 256;
}

Cancellation::Cancellation(
    const std::atomic<bool> &cancelled,
    std::chrono::steady_clock::time_point deadline)
    : cancelled_(cancelled), deadline_(deadline) {}

bool Cancellation::requested() const noexcept {
  return cancelled_.load(std::memory_order_acquire);
}

bool Cancellation::deadlineReached() const noexcept {
  return std::chrono::steady_clock::now() >= deadline_;
}

Worker::Worker(Backend &backend, unsigned max_frames)
    : backend_(backend),
      max_frames_(max_frames),
      slots_{Slot(max_frames), Slot(max_frames)},
      thread_(&Worker::run, this) {}

Worker::~Worker() {
  {
    std::lock_guard<std::mutex> lock(mutex_);
    stopping_ = true;
    for (auto &slot : slots_) slot.cancelled.store(true);
  }
  wake_.notify_all();
  if (thread_.joinable()) thread_.join();
}

SubmitResult Worker::captureCompleted(std::uint64_t generation,
                                      std::chrono::milliseconds timeout,
                                      CaptureSource &source) {
  if (!generation || timeout.count() <= 0 || !max_frames_)
    return {SubmitStatus::CaptureFailed, -EINVAL};

  Slot *selected = nullptr;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (stopping_) return {SubmitStatus::Stopped, -ECANCELED};
    if (generation <= newest_generation_ || generation <= cancelled_through_)
      return {SubmitStatus::Stale, -EALREADY};
    for (auto &slot : slots_) {
      if (slot.state == SlotState::Free) {
        selected = &slot;
        break;
      }
    }
    if (!selected) return {SubmitStatus::Busy, -EBUSY};

    // A later completed recording supersedes older queued/running work. The
    // active backend owns its buffer until it acknowledges cancellation.
    newest_generation_ = generation;
    for (auto &slot : slots_) {
      if (slot.state != SlotState::Free && slot.generation < generation) {
        slot.cancelled.store(true, std::memory_order_release);
        if (slot.state == SlotState::Queued) {
          pushResultLocked(
              {slot.generation, ResultStatus::Cancelled, -ECANCELED, {}});
          releaseLocked(slot);
        }
      }
    }
    selected->generation = generation;
    selected->frames = 0;
    selected->deadline = std::chrono::steady_clock::now() + timeout;
    selected->cancelled.store(false, std::memory_order_release);
    selected->state = SlotState::Filling;
  }

  unsigned frames = 0;
  int error = 0;
  try {
    error = source.copyMono(selected->samples.data(), max_frames_, &frames);
  } catch (...) {
    error = -EIO;
  }
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (error || !frames || frames > max_frames_) {
      releaseLocked(*selected);
      return {SubmitStatus::CaptureFailed,
              error ? error : (frames > max_frames_ ? -EOVERFLOW : -ENODATA)};
    }
    selected->frames = frames;
    if (stopping_ || selected->cancelled.load() ||
        generation <= cancelled_through_) {
      pushResultLocked({generation, ResultStatus::Cancelled, -ECANCELED, {}});
      releaseLocked(*selected);
      return {SubmitStatus::Cancelled, -ECANCELED};
    }
    selected->state = SlotState::Queued;
  }
  wake_.notify_one();
  return {SubmitStatus::Accepted, 0};
}

void Worker::cancelThrough(std::uint64_t generation) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (generation > cancelled_through_) cancelled_through_ = generation;
  for (auto &slot : slots_) {
    if (slot.state == SlotState::Free || slot.generation > generation) continue;
    slot.cancelled.store(true, std::memory_order_release);
    if (slot.state == SlotState::Queued) {
      pushResultLocked(
          {slot.generation, ResultStatus::Cancelled, -ECANCELED, {}});
      releaseLocked(slot);
    }
  }
  wake_.notify_all();
}

bool Worker::poll(Result &result) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (results_.empty()) return false;
  result = std::move(results_.front());
  results_.pop_front();
  return true;
}

std::size_t Worker::droppedResults() const {
  std::lock_guard<std::mutex> lock(mutex_);
  return dropped_results_;
}

void Worker::pushResultLocked(Result result) {
  if (results_.size() == kResultCapacity) {
    results_.pop_front();
    ++dropped_results_;
  }
  results_.push_back(std::move(result));
}

void Worker::releaseLocked(Slot &slot) {
  slot.frames = 0;
  slot.generation = 0;
  slot.cancelled.store(false, std::memory_order_release);
  slot.state = SlotState::Free;
}

void Worker::run() {
  for (;;) {
    Slot *selected = nullptr;
    {
      std::unique_lock<std::mutex> lock(mutex_);
      wake_.wait(lock, [&] {
        if (stopping_) return true;
        for (auto &slot : slots_)
          if (slot.state == SlotState::Queued) return true;
        return false;
      });
      if (stopping_) {
        for (auto &slot : slots_) {
          if (slot.state == SlotState::Queued) releaseLocked(slot);
        }
        return;
      }
      for (auto &slot : slots_) {
        if (slot.state == SlotState::Queued &&
            (!selected || slot.generation > selected->generation))
          selected = &slot;
      }
      if (!selected) {
        if (stopping_) return;
        continue;
      }
      selected->state = SlotState::Running;
    }

    std::string text;
    Cancellation cancellation(selected->cancelled, selected->deadline);
    int error = 0;
    try {
      error = backend_.recognize(selected->samples.data(), selected->frames,
                                 cancellation, text);
    } catch (...) {
      error = -EIO;
      text.clear();
    }

    std::lock_guard<std::mutex> lock(mutex_);
    const auto generation = selected->generation;
    const bool timed_out = cancellation.deadlineReached();
    const bool cancelled = selected->cancelled.load() ||
                           generation <= cancelled_through_ || stopping_;
    if (timed_out)
      pushResultLocked(
          {generation, ResultStatus::TimedOut, -ETIMEDOUT, {}});
    else if (cancelled)
      pushResultLocked(
          {generation, ResultStatus::Cancelled, -ECANCELED, {}});
    else if (error || text.empty())
      pushResultLocked({generation, ResultStatus::Failed,
                        error ? error : -ENODATA, {}});
    else
      pushResultLocked(
          {generation, ResultStatus::Completed, 0, std::move(text)});
    releaseLocked(*selected);
    if (stopping_) return;
  }
}

int K7SoundCaptureSource::copyMono(float *destination, unsigned capacity,
                                   unsigned *frames) {
  return k7sound_copy_mono(destination, capacity, frames);
}

int LegacyMicrophoneTextBackend::recognize(
    const float *, unsigned, const Cancellation &cancellation,
    std::string &text) {
  if (cancellation.requested()) return -ECANCELED;
  char buffer[kLegacyTextCapacity]{};
  const int error = k7_asr_microphone_text(buffer, sizeof(buffer));
  if (error) return error;
  if (cancellation.requested()) return -ECANCELED;
  if (cancellation.deadlineReached()) return -ETIMEDOUT;
  text.assign(buffer);
  return text.empty() ? -ENODATA : 0;
}

}  // namespace capture_asr
