#pragma once

#include <cstddef>
#include <cstdint>

namespace voice_prompt {

enum class Result {
  Ok,
  InvalidArgument,
  ResourceMissing,
  ResourceIo,
  UnsupportedFormat,
  Busy,
  Cancelled,
  SinkError,
  CleanupError,
};

struct PlaybackStats {
  std::uint32_t source_bytes{};
  std::uint32_t frames_submitted{};
  std::uint32_t write_calls{};
};

// A backend may resolve prompt_id to a ROM table, a read-only filesystem, or
// another immutable store. read() returns 0 at EOF, a negative value on error,
// and may legally return fewer bytes than requested.
class ResourcePort {
 public:
  virtual ~ResourcePort() = default;
  virtual Result open(const char* prompt_id) noexcept = 0;
  virtual std::ptrdiff_t read(std::uint8_t* destination,
                              std::size_t capacity) noexcept = 0;
  virtual void close() noexcept = 0;
};

// The sink consumes signed 32-bit stereo slots at 16 kHz. writeFrames() may
// accept a short prefix. abort() must make partially started hardware safe and
// is required to be idempotent. acquire() is the sole ownership gate.
class AudioSinkPort {
 public:
  virtual ~AudioSinkPort() = default;
  virtual Result acquire() noexcept = 0;
  virtual bool begin(std::uint32_t sample_rate, std::uint8_t channels) noexcept = 0;
  virtual std::ptrdiff_t writeFrames(const std::int32_t* interleaved_stereo,
                                     std::size_t frames) noexcept = 0;
  virtual bool finish() noexcept = 0;
  virtual bool abort() noexcept = 0;
  virtual void release() noexcept = 0;
};

class CancelPort {
 public:
  virtual ~CancelPort() = default;
  virtual bool requested() const noexcept = 0;
};

// Accepts RIFF/WAVE PCM16, mono, 16 kHz resources. Samples are expanded to
// signed 32-bit stereo slots without gain. Working storage is bounded and no
// pointer into the resource is retained after return.
Result playFixedPrompt(const char* prompt_id, ResourcePort& resource,
                       AudioSinkPort& sink, const CancelPort& cancel,
                       PlaybackStats* stats) noexcept;

const char* resultName(Result result) noexcept;

}  // namespace voice_prompt
