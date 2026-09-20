#pragma once

#include "voicelink/types.hpp"

#include <string>
#include <vector>

namespace voicelink {

// Distinct I/O outcome so that false / empty-vector never ambiguously encodes
// multiple states (timeout, retryable, EOF, fatal, -ENOSYS).
enum class IoStatus {
  Ok,
  Timeout,
  RetryableError,
  EndOfInput,
  FatalError,
};

struct ScanResult {
  IoStatus status{IoStatus::Ok};
  std::vector<AccessPoint> access_points;
  int error_code{};
};

class TtsPort {
 public:
  virtual ~TtsPort() = default;
  virtual bool speak(const std::string& text) = 0;
  virtual void stop() = 0;
};

class WifiPort {
 public:
  virtual ~WifiPort() = default;
  virtual ScanResult scan() = 0;
  // Connection methods are bounded/nonblocking, noexcept, never call Controller.
  // beginConnect must copy needed credentials before returning, never retain
  // the caller pointer or log secrets; erase its copy on completion/cancel.
  // IDs are unique for this port lifetime, including rejected attempts.
  virtual ConnectResult beginConnect(const std::string& ssid, const char* password,
                                    std::size_t password_len) noexcept = 0;
  virtual ConnectResult pollConnect(std::uint64_t request_id) noexcept = 0;
  // Cancel only this transaction; idempotent. Never disconnect another client.
  virtual void cancelConnect(std::uint64_t request_id) noexcept = 0;

};

class ClockPort {
 public:
  virtual ~ClockPort() = default;
  virtual std::uint64_t nowMs() const noexcept = 0; // monotonic milliseconds
};

class TextInputPort {
 public:
  virtual ~TextInputPort() = default;
  // Fill *text* with recognized UTF-8 and return Ok.
  // Return Timeout when no speech arrived within the listen window (keep waiting).
  // Return RetryableError for transient ASR errors (brief prompt, retry grammar).
  // Return EndOfInput when the source is exhausted (clear passwords, exit).
  // Return FatalError for unrecoverable errors (enter State::Error).
  virtual IoStatus next(Grammar grammar, std::string& text) = 0;
};

}  // namespace voicelink
