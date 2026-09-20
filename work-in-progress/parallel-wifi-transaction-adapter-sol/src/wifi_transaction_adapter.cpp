#include "wifi_transaction_adapter.hpp"

#include <cstdio>

namespace voicelink::wifi_transaction {
namespace {

constexpr int kProtocolError = -7101;
constexpr int kPollError = -7102;

bool usableIpv4(const std::uint8_t ip[4]) noexcept {
  return ip[0] != 0 && ip[0] != 127 && ip[0] < 224 &&
         !(ip[0] == 169 && ip[1] == 254);
}

ConnectStatus failureStatus(FailureReason reason) noexcept {
  switch (reason) {
    case FailureReason::Authentication:
      return ConnectStatus::WrongPassword;
    case FailureReason::NetworkNotFound:
      return ConnectStatus::NetworkNotFound;
    case FailureReason::UnsupportedSecurity:
      return ConnectStatus::Unsupported;
    default:
      return ConnectStatus::Failed;
  }
}

}  // namespace

WifiTransactionAdapter::WifiTransactionAdapter(WifiPort& scan_delegate,
                                               TransactionBackend& backend,
                                               std::uint64_t timeout_ms) noexcept
    : scan_delegate_(scan_delegate), backend_(backend), timeout_ms_(timeout_ms) {}

ScanResult WifiTransactionAdapter::beginScan() { return scan_delegate_.beginScan(); }

ScanResult WifiTransactionAdapter::pollScan(std::uint64_t request_id) {
  return scan_delegate_.pollScan(request_id);
}

void WifiTransactionAdapter::cancelScan(std::uint64_t request_id) noexcept {
  scan_delegate_.cancelScan(request_id);
}

ConnectResult WifiTransactionAdapter::beginConnect(const std::string& ssid,
                                                   const char* password,
                                                   std::size_t password_len) noexcept {
  const SubmitReply reply =
      backend_.submitCredentials(ssid, password, password_len, timeout_ms_);
  ConnectResult out;
  out.request_id = reply.transaction_id;
  out.error_code = reply.error_code;
  switch (reply.status) {
    case SubmitStatus::Accepted:
      if (!reply.transaction_id) {
        out.status = ConnectStatus::Failed;
        out.error_code = kProtocolError;
        return out;
      }
      active_id_ = reply.transaction_id;
      cancelled_id_ = 0;
      last_sequence_ = 0;
      last_progress_ = {};
      last_progress_.transaction_id = reply.transaction_id;
      last_progress_.stage = Stage::Accepted;
      last_result_ = {ConnectStatus::CredentialsReceived, 0,
                      reply.transaction_id, {}};
      return last_result_;
    case SubmitStatus::Busy:
      out.status = ConnectStatus::Busy;
      break;
    case SubmitStatus::Unsupported:
      out.status = ConnectStatus::Unsupported;
      break;
    default:
      out.status = ConnectStatus::Failed;
      break;
  }
  return out;
}

ConnectResult WifiTransactionAdapter::translate(const Snapshot& snapshot) const noexcept {
  ConnectResult out;
  out.request_id = snapshot.transaction_id;
  out.error_code = snapshot.error_code;
  switch (snapshot.stage) {
    case Stage::Accepted:
      out.status = ConnectStatus::CredentialsReceived;
      return out;
    case Stage::InProgress:
    case Stage::Authenticated:
    case Stage::Dhcp:
      out.status = ConnectStatus::Connecting;
      return out;
    case Stage::IpReady:
      if (!snapshot.authenticated || !snapshot.dhcp_acquired ||
          !snapshot.link_up || !snapshot.lease_held ||
          !snapshot.operation_complete || !usableIpv4(snapshot.ipv4)) {
        out.status = ConnectStatus::Failed;
        out.error_code = kProtocolError;
        return out;
      }
      {
        char ip[16];
        std::snprintf(ip, sizeof(ip), "%u.%u.%u.%u", snapshot.ipv4[0],
                      snapshot.ipv4[1], snapshot.ipv4[2], snapshot.ipv4[3]);
#if defined(__cpp_exceptions) || defined(__EXCEPTIONS)
        try {
          out.ipv4 = ip;
          out.status = ConnectStatus::IpReady;
        } catch (...) {
          out.status = ConnectStatus::Failed;
          out.error_code = -12;
        }
#else
        out.ipv4 = ip;
        out.status = ConnectStatus::IpReady;
#endif
      }
      return out;
    case Stage::Failed:
      out.status = failureStatus(snapshot.failure_reason);
      return out;
    case Stage::Cancelled:
      out.status = ConnectStatus::Cancelled;
      return out;
    case Stage::Timeout:
      out.status = ConnectStatus::Timeout;
      return out;
  }
  out.status = ConnectStatus::Failed;
  out.error_code = kProtocolError;
  return out;
}

ConnectResult WifiTransactionAdapter::pollConnect(std::uint64_t request_id) noexcept {
  Snapshot snapshot{};
  if (!request_id || !backend_.poll(request_id, snapshot)) {
    return {ConnectStatus::Failed, kPollError, request_id, {}};
  }

  // Preserve the producer's ID. Controller's existing request-id check drops
  // this old/foreign event; it must never be relabelled as the current request.
  if (snapshot.transaction_id != request_id) return translate(snapshot);

  // A cancel acknowledgement is not required before suppressing late success.
  if (cancelled_id_ == request_id) {
    return {ConnectStatus::Cancelled, 0, request_id, {}};
  }

  if (!snapshot.sequence) {
    return {ConnectStatus::Failed, kProtocolError, request_id, {}};
  }
  if (request_id == active_id_ && snapshot.sequence <= last_sequence_) {
    return last_result_;  // duplicate/out-of-order event cannot regress state
  }

  ConnectResult result = translate(snapshot);
  if (request_id == active_id_) {
    last_sequence_ = snapshot.sequence;
    last_progress_ = snapshot;
    last_result_ = result;
    if (snapshot.stage == Stage::IpReady || snapshot.stage == Stage::Failed ||
        snapshot.stage == Stage::Cancelled || snapshot.stage == Stage::Timeout) {
      active_id_ = 0;
    }
  }
  return result;
}

void WifiTransactionAdapter::cancelConnect(std::uint64_t request_id) noexcept {
  if (!request_id || cancelled_id_ == request_id) return;
  cancelled_id_ = request_id;
  if (active_id_ == request_id) {
    last_result_ = {ConnectStatus::Cancelled, 0, request_id, {}};
    active_id_ = 0;
  }
  backend_.cancel(request_id);
}

}  // namespace voicelink::wifi_transaction
