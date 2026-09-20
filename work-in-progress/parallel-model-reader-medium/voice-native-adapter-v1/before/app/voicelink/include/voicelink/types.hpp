#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace voicelink {

enum class State {
  WaitingWake,
  ScanningWifi,
  WaitingNetworkChoice,
  EnteringPassword,
  CredentialsReceived,
  ConnectingWifi,
  Completed,
  Error,
  Idle,
};

enum class Grammar { WakeWord, NetworkSelection, PasswordToken };
enum class PasswordControl { Finish, DeleteLast, Clear, Restart, Cancel, ReportLength,
                             SwitchUpper, SwitchLower };
enum class PasswordMode { Lower, Upper };

struct AccessPoint {
  std::string ssid;
  int rssi{};
  bool secured{};
};

struct PasswordToken {
  std::optional<char> character;
  std::optional<PasswordControl> control;
  bool case_explicit{false}; /* true if 大写/小写 prefix was used */
};

// 大赛统一唤醒词（contest_overview.md：若项目包含 AI 语音唤醒功能，统一使用
// 指定唤醒词「你好，openvela / Hello，openvela」）。
// 这里保存的是 normalize() 之后的形态：ASCII 小写、无空格、无标点。
// 裸 openvela 一并保留，兼容调试与硬件侧既有 KWS 词表。
// isWakeWord() 还会自动剥掉一层礼貌前缀，因此「您好，openvela」「嗨 openvela」
// 等口语变体同样能唤醒；「小信」「openvela123」等近似音不会误唤醒。
inline const std::vector<std::string>& defaultWakeWords() {
  static const std::vector<std::string> words{"你好openvela", "helloopenvela", "openvela"};
  return words;
}

struct Config {
  std::vector<std::string> wake_words{defaultWakeWords()};
  std::string greeting{"你好，我是 openvela，开始为你配置网络"};
  std::size_t max_networks{5};
  std::uint64_t connect_timeout_ms{30000};
  std::uint64_t scan_timeout_ms{30000};
  std::size_t min_password_length{8};
  std::size_t max_password_length{63};
};

// Receipt/association is not IP readiness. No legacy synchronous Ok status.
enum class ConnectStatus {
  CredentialsReceived, Connecting, IpReady, WrongPassword, Timeout,
  NetworkNotFound, Failed, Busy, Unsupported, Cancelled
};
struct ConnectResult {
  ConnectStatus status{ConnectStatus::Failed};
  int error_code{};
  std::uint64_t request_id{};
  std::string ipv4;
};

struct Context {
  State state{State::WaitingWake};
  Grammar grammar{Grammar::WakeWord};
  std::vector<AccessPoint> candidates;
  std::optional<std::size_t> selected_index;
  std::vector<char> password;
  PasswordMode password_mode{PasswordMode::Lower};
};

}  // namespace voicelink
