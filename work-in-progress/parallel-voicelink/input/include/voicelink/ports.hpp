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
  // password may be nullptr when joining an open network. Never log it.
  virtual ConnectResult connect(const std::string& ssid, const char* password,
                                std::size_t password_len) = 0;
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
