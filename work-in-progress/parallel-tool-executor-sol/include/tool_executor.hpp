#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace velavision::tools {

constexpr std::size_t kMaxRequestBytes = 256;
constexpr std::size_t kMaxResponseBytes = 192;
constexpr std::size_t kMaxTransactions = 8;

enum class Tool { PhotoCapture, DeviceStatus, NetworkScan };
enum class ParseError { None, TooLarge, Syntax, Schema, UnknownTool, SensitiveField };

struct Call {
  Tool tool{Tool::DeviceStatus};
  std::uint32_t timeout_ms{};
  std::uint8_t camera{};
  std::uint8_t scan_limit{};
};

struct ParseResult {
  ParseError error{ParseError::Syntax};
  Call call{};
  explicit operator bool() const noexcept { return error == ParseError::None; }
};

ParseResult parseModelCall(std::string_view input) noexcept;

enum class PortState { Running, Succeeded, Failed };
enum class PortError { None, Rejected, Execution, Protocol };

struct PortResult {
  PortState state{PortState::Failed};
  PortError error{PortError::Protocol};
  // Fixed, typed result fields. The executor never accepts result JSON from a
  // model and never treats an accepted request as completion.
  char asset_id[40]{};
  bool wifi_connected{};
  std::uint8_t battery_percent{};
  std::array<std::array<char, 33>, 8> ssids{};
  std::uint8_t ssid_count{};
};

class ExecutionPort {
 public:
  virtual ~ExecutionPort() = default;
  virtual bool start(std::uint64_t transaction_id, const Call& call) noexcept = 0;
  virtual PortResult poll(std::uint64_t transaction_id) noexcept = 0;
  virtual void cancel(std::uint64_t transaction_id) noexcept = 0;
};

enum class State { Empty, Accepted, Running, Succeeded, Failed, Cancelled, TimedOut };
enum class SubmitError { None, InvalidRequestId, DuplicateRequestId, Parse, Capacity, PortRejected, IdExhausted };

struct SubmitResult {
  SubmitError error{SubmitError::None};
  ParseError parse_error{ParseError::None};
  std::uint64_t transaction_id{};
  State state{State::Empty};
};

struct Response {
  std::array<char, kMaxResponseBytes> bytes{};
  std::size_t size{};
  bool truncated{};
  std::string_view view() const noexcept { return {bytes.data(), size}; }
};

class Executor {
 public:
  explicit Executor(ExecutionPort& port) noexcept : port_(port) {}

  SubmitResult submit(std::uint64_t trusted_request_id,
                      std::string_view model_json,
                      std::uint64_t now_ms) noexcept;
  State poll(std::uint64_t trusted_request_id, std::uint64_t now_ms) noexcept;
  bool cancel(std::uint64_t trusted_request_id) noexcept;
  Response response(std::uint64_t trusted_request_id) const noexcept;

 private:
  struct Entry {
    std::uint64_t request_id{};
    std::uint64_t transaction_id{};
    std::uint64_t deadline_ms{};
    State state{State::Empty};
    Call call{};
    PortResult result{};
  };

  Entry* find(std::uint64_t request_id) noexcept;
  const Entry* find(std::uint64_t request_id) const noexcept;

  ExecutionPort& port_;
  std::array<Entry, kMaxTransactions> entries_{};
  std::uint64_t next_transaction_id_{1};
};

// Deterministic host-only implementation of the real port interface. It
// exercises start/poll/cancel without network, camera, device, or credential I/O.
class FakeExecutionPort final : public ExecutionPort {
 public:
  enum class Mode { Success, StartFailure, ExecutionFailure, NeverCompletes, OversizedScan };
  explicit FakeExecutionPort(Mode mode = Mode::Success) noexcept : mode_(mode) {}
  bool start(std::uint64_t transaction_id, const Call& call) noexcept override;
  PortResult poll(std::uint64_t transaction_id) noexcept override;
  void cancel(std::uint64_t transaction_id) noexcept override;
  bool cancel_seen() const noexcept { return cancel_seen_; }

 private:
  Mode mode_;
  std::uint64_t active_id_{};
  Call active_call_{};
  unsigned polls_{};
  bool cancel_seen_{};
};

}  // namespace velavision::tools
