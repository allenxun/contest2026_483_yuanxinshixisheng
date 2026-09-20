#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace vela::voice_provision {

enum class State {
  WaitingWake,
  Scanning,
  ChoosingNetwork,
  EnteringPassword,
  ConfirmingPassword,
  CredentialsAccepted,
  AuthenticatingWpa2,
  AcquiringDhcp,
  Completed,
  Idle,
  Error,
};

enum class Grammar { Wake, NetworkChoice, PasswordToken, Confirmation, CancelOnly };
enum class ScanStatus { Accepted, Running, Ready, Busy, Unsupported, Timeout, Cancelled, Failed };
enum class LinkStatus {
  CredentialsAccepted,
  Wpa2Authenticating,
  Wpa2Authenticated,
  DhcpAcquiring,
  IpReady,
  WrongPassword,
  NetworkNotFound,
  Timeout,
  Cancelled,
  Busy,
  Unsupported,
  Failed,
};

struct AccessPoint { std::string ssid; int rssi{}; bool secured{}; };
struct ScanEvent {
  std::uint64_t request_id{};
  ScanStatus status{ScanStatus::Failed};
  std::vector<AccessPoint> access_points;
  int error_code{};
};
struct LinkEvent {
  std::uint64_t request_id{};
  LinkStatus status{LinkStatus::Failed};
  std::string ipv4;
  int error_code{};
};

class VoiceOutput {
 public:
  virtual ~VoiceOutput() = default;
  virtual bool speak(const std::string&) = 0;
  virtual void stop() noexcept = 0;
};

class WifiService {
 public:
  virtual ~WifiService() = default;
  virtual ScanEvent beginScan() noexcept = 0;
  virtual ScanEvent pollScan(std::uint64_t) noexcept = 0;
  virtual void cancelScan(std::uint64_t) noexcept = 0;
  // Equivalent to the trusted voice path ending in submit_credentials. The
  // implementation must copy, then wipe, its private credential buffer.
  virtual LinkEvent submitCredentials(const std::string& ssid,
                                      const char* password,
                                      std::size_t password_len) noexcept = 0;
  virtual LinkEvent pollLink(std::uint64_t) noexcept = 0;
  virtual void cancelLink(std::uint64_t) noexcept = 0;
};

class Clock { public: virtual ~Clock() = default; virtual std::uint64_t nowMs() const noexcept = 0; };

struct Config {
  std::uint64_t scan_timeout_ms{30000};
  std::uint64_t input_timeout_ms{60000};
  std::uint64_t connect_timeout_ms{30000};
  std::size_t max_networks{5};
  std::size_t min_password_length{8};
  std::size_t max_password_length{63};
};

struct Snapshot {
  State state{State::WaitingWake};
  Grammar grammar{Grammar::Wake};
  std::vector<AccessPoint> candidates;
  std::optional<std::size_t> selected_index;
  std::size_t password_length{}; // credential bytes are intentionally opaque
};

class Machine {
 public:
  Machine(VoiceOutput&, WifiService&, Clock&, Config = {});
  ~Machine();
  void start();
  void ingest(const std::string& recognized_text);
  void poll();
  void cancel();
  const Snapshot& snapshot() const noexcept { return view_; }

 private:
  void beginScan();
  void applyScan(ScanEvent);
  void applyLink(LinkEvent);
  void choose(const std::string&);
  void password(const std::string&);
  void confirmation(const std::string&);
  void say(const std::string&);
  void terminal(State, const std::string&);
  void wipePassword() noexcept;
  void clearTransactions() noexcept;
  void touch() noexcept;

  VoiceOutput& voice_;
  WifiService& wifi_;
  Clock& clock_;
  Config config_;
  Snapshot view_;
  std::vector<char> password_;
  std::uint64_t scan_id_{};
  std::uint64_t link_id_{};
  std::uint64_t deadline_ms_{};
};

} // namespace vela::voice_provision
