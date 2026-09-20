#include "tool_executor.hpp"

#include <cstdlib>
#include <iostream>
#include <string>

using namespace velavision::tools;

namespace {
int checks = 0;
void expect(bool value, const char* message) { ++checks; if (!value) { std::cerr << "FAIL " << message << '\n'; std::exit(1); } }
class MultiPort final : public ExecutionPort {
 public:
  bool start(std::uint64_t, const Call&) noexcept override { return true; }
  PortResult poll(std::uint64_t) noexcept override { return {PortState::Running, PortError::None}; }
  void cancel(std::uint64_t) noexcept override {}
};
constexpr std::string_view kPhoto = R"({"version":1,"tool":"photo.capture","args":{"camera":2},"timeout_ms":100})";
constexpr std::string_view kStatus = R"({"version":1,"tool":"device.status","args":{},"timeout_ms":100})";
constexpr std::string_view kScan = R"({"version":1,"tool":"network.scan","args":{"limit":2},"timeout_ms":100})";
constexpr std::string_view kLargeScan = R"({"version":1,"tool":"network.scan","args":{"limit":8},"timeout_ms":100})";
}

int main() {
  expect(parseModelCall(kPhoto).call.camera == 2, "photo parse");
  expect(parseModelCall(kStatus).call.tool == Tool::DeviceStatus, "status parse");
  expect(parseModelCall(kScan).call.scan_limit == 2, "scan parse");
  expect(parseModelCall(R"({"version":1,"tool":"shell.exec","args":{},"timeout_ms":1})").error == ParseError::UnknownTool, "unknown tool");
  expect(!parseModelCall(R"({"version":1,"tool":"network.scan","args":{"limit":9},"timeout_ms":1})"), "range validation");
  expect(parseModelCall(R"({"version":1,"tool":"device.status","args":{"password":"DO_NOT_LOG_SECRET"},"timeout_ms":1})").error == ParseError::SensitiveField, "password blocked");
  expect(!parseModelCall(R"({"version":1,"tool":"device.status","args":{},"timeout_ms":1,"success":true})"), "model success rejected");

  FakeExecutionPort port;
  Executor executor(port);
  auto first = executor.submit(41, kPhoto, 1000);
  expect(first.error == SubmitError::None && first.state == State::Accepted && first.transaction_id != 0, "accepted is not success");
  expect(executor.submit(41, kStatus, 1000).error == SubmitError::DuplicateRequestId, "duplicate request id");
  expect(executor.poll(41, 1001) == State::Running, "real port running");
  expect(executor.poll(41, 1002) == State::Succeeded, "real port success");
  const std::string photo_response(executor.response(41).view());
  expect(photo_response.find("fake-photo-camera-2") != std::string::npos, "real port result returned");
  expect(photo_response.find("DO_NOT_LOG_SECRET") == std::string::npos, "secret absent from response");

  FakeExecutionPort status_port;
  Executor status_executor(status_port);
  expect(status_executor.submit(42, kStatus, 0).error == SubmitError::None, "status submit");
  status_executor.poll(42, 1); status_executor.poll(42, 2);
  expect(status_executor.response(42).view().find("\"battery_percent\":73") != std::string_view::npos, "status result returned");

  FakeExecutionPort cancel_port(FakeExecutionPort::Mode::NeverCompletes);
  Executor cancel_executor(cancel_port);
  expect(cancel_executor.submit(1, kStatus, 0).error == SubmitError::None, "cancel submit");
  expect(cancel_executor.cancel(1) && cancel_port.cancel_seen(), "cancel reaches port");
  expect(cancel_executor.poll(1, 50) == State::Cancelled, "late poll stays cancelled");

  FakeExecutionPort timeout_port(FakeExecutionPort::Mode::NeverCompletes);
  Executor timeout_executor(timeout_port);
  expect(timeout_executor.submit(2, kStatus, 100).error == SubmitError::None, "timeout submit");
  expect(timeout_executor.poll(2, 200) == State::TimedOut && timeout_port.cancel_seen(), "deadline cancels port");

  FakeExecutionPort fail_port(FakeExecutionPort::Mode::ExecutionFailure);
  Executor fail_executor(fail_port);
  expect(fail_executor.submit(3, kStatus, 0).error == SubmitError::None, "failure submit");
  expect(fail_executor.poll(3, 1) == State::Running, "failure initially running");
  expect(fail_executor.poll(3, 2) == State::Failed, "execution failure propagated");
  expect(fail_executor.response(3).view().find("execution_failed") != std::string_view::npos, "failure response");

  FakeExecutionPort start_fail_port(FakeExecutionPort::Mode::StartFailure);
  Executor start_fail_executor(start_fail_port);
  expect(start_fail_executor.submit(30, kStatus, 0).error == SubmitError::PortRejected, "start failure propagated");

  FakeExecutionPort scan_port(FakeExecutionPort::Mode::OversizedScan);
  Executor scan_executor(scan_port);
  expect(scan_executor.submit(4, kScan, 0).error == SubmitError::None, "scan submit");
  scan_executor.poll(4, 1); scan_executor.poll(4, 2);
  const auto bounded = scan_executor.response(4);
  expect(bounded.size <= kMaxResponseBytes, "response capacity");
  expect(bounded.view().find("fake-network-1") != std::string_view::npos && bounded.view().find("fake-network-2") == std::string_view::npos, "scan result limited");

  FakeExecutionPort overflow_port(FakeExecutionPort::Mode::OversizedScan);
  Executor overflow_executor(overflow_port);
  expect(overflow_executor.submit(5, kLargeScan, 0).error == SubmitError::None, "large response submit");
  overflow_executor.poll(5, 1); overflow_executor.poll(5, 2);
  const auto overflow = overflow_executor.response(5);
  expect(overflow.truncated && overflow.view() == R"({"error":"response_too_large"})", "response overflow becomes bounded error");

  MultiPort capacity_port;
  Executor capacity_executor(capacity_port);
  for (std::uint64_t i = 1; i <= kMaxTransactions; ++i) expect(capacity_executor.submit(i, kStatus, 0).error == SubmitError::None, "ledger fill");
  expect(capacity_executor.submit(99, kStatus, 0).error == SubmitError::Capacity, "ledger capacity");

  std::cout << "PASS checks=" << checks << '\n';
  return 0;
}
