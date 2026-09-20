#pragma once

#include "voicelink/ports.hpp"

#include <cstddef>
#include <cstdint>
#include <string>

namespace voicelink::wifi_transaction {

enum class SubmitStatus {
  Accepted,
  Busy,
  Unsupported,
  Invalid,
  Unavailable,
  Failed,
};

enum class Stage {
  Accepted,
  InProgress,
  Authenticated,
  Dhcp,
  IpReady,
  Failed,
  Cancelled,
  Timeout,
};

enum class FailureReason {
  None,
  Authentication,
  NetworkNotFound,
  UnsupportedSecurity,
  Backend,
  Protocol,
};

struct SubmitReply {
  SubmitStatus status{SubmitStatus::Failed};
  std::uint64_t transaction_id{};
  int error_code{};
};

// Immutable transaction event returned by the shared k7radio service.
// sequence is strictly increasing within one transaction and never zero.
struct Snapshot {
  std::uint64_t transaction_id{};
  std::uint64_t sequence{};
  Stage stage{Stage::Failed};
  FailureReason failure_reason{FailureReason::None};
  int error_code{};
  bool authenticated{};
  bool dhcp_acquired{};
  bool link_up{};
  bool lease_held{};
  bool operation_complete{};
  std::uint8_t ipv4[4]{};
};

class TransactionBackend {
 public:
  virtual ~TransactionBackend() = default;
  // The backend copies credentials before returning Accepted. It must not log
  // or retain the caller's pointers. Every valid-context reply has a unique ID.
  virtual SubmitReply submitCredentials(const std::string& ssid,
                                        const char* password,
                                        std::size_t password_len,
                                        std::uint64_t timeout_ms) noexcept = 0;
  // May surface an older transaction event. Its original transaction_id must
  // be preserved so Controller can reject it as stale/foreign.
  virtual bool poll(std::uint64_t transaction_id, Snapshot& out) noexcept = 0;
  // Receipt of cancel is not a quiescence fence and does not release RF lease.
  virtual void cancel(std::uint64_t transaction_id) noexcept = 0;
};

// Candidate connection adapter. Scan stays delegated to the already tested
// shared scan adapter; this class changes no scan ownership or radio behavior.
class WifiTransactionAdapter final : public WifiPort {
 public:
  WifiTransactionAdapter(WifiPort& scan_delegate,
                         TransactionBackend& backend,
                         std::uint64_t timeout_ms = 30000) noexcept;

  ScanResult beginScan() override;
  ScanResult pollScan(std::uint64_t request_id) override;
  void cancelScan(std::uint64_t request_id) noexcept override;

  ConnectResult beginConnect(const std::string& ssid,
                             const char* password,
                             std::size_t password_len) noexcept override;
  ConnectResult pollConnect(std::uint64_t request_id) noexcept override;
  void cancelConnect(std::uint64_t request_id) noexcept override;

  const Snapshot& lastProgress() const noexcept { return last_progress_; }
  std::uint64_t activeTransaction() const noexcept { return active_id_; }

 private:
  ConnectResult translate(const Snapshot& snapshot) const noexcept;

  WifiPort& scan_delegate_;
  TransactionBackend& backend_;
  std::uint64_t timeout_ms_;
  std::uint64_t active_id_{};
  std::uint64_t cancelled_id_{};
  std::uint64_t last_sequence_{};
  Snapshot last_progress_{};
  ConnectResult last_result_{};
};

}  // namespace voicelink::wifi_transaction
