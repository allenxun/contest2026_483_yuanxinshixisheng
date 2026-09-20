#include "wifi_transaction_adapter.hpp"

#include "voicelink/controller.hpp"

#include <cassert>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

using namespace voicelink;
using namespace voicelink::wifi_transaction;

struct ScanDelegate final : WifiPort {
  std::uint64_t scan_id{41};
  unsigned scan_cancels{};
  ScanResult beginScan() override { return {ScanStatus::Received, {}, 0, scan_id}; }
  ScanResult pollScan(std::uint64_t id) override {
    return {ScanStatus::Ready, {{"VoiceTest", -20, true}}, 0, id};
  }
  void cancelScan(std::uint64_t) noexcept override { ++scan_cancels; }
  ConnectResult beginConnect(const std::string&, const char*, std::size_t) noexcept override {
    assert(false && "connection must use transaction backend");
    return {};
  }
  ConnectResult pollConnect(std::uint64_t) noexcept override {
    assert(false && "connection must use transaction backend");
    return {};
  }
  void cancelConnect(std::uint64_t) noexcept override {
    assert(false && "connection must use transaction backend");
  }
};

struct FakeBackend final : TransactionBackend {
  SubmitReply submit{SubmitStatus::Accepted, 77, 0};
  Snapshot next{};
  bool poll_ok{true};
  unsigned submits{};
  unsigned cancels{};
  std::uint64_t cancelled_id{};
  std::string copied_ssid;
  std::vector<char> copied_password;

  SubmitReply submitCredentials(const std::string& ssid, const char* password,
                                std::size_t password_len,
                                std::uint64_t timeout_ms) noexcept override {
    ++submits;
    assert(timeout_ms == 30000);
    copied_ssid = ssid;
    copied_password.assign(password, password + password_len);
    return submit;
  }
  bool poll(std::uint64_t, Snapshot& out) noexcept override {
    out = next;
    return poll_ok;
  }
  void cancel(std::uint64_t id) noexcept override {
    ++cancels;
    cancelled_id = id;
  }
};

struct Clock final : ClockPort {
  std::uint64_t ms{};
  std::uint64_t nowMs() const noexcept override { return ms; }
};

struct Speaker final : TtsPort {
  std::vector<std::string> messages;
  bool speak(const std::string& text) override { messages.push_back(text); return true; }
  void stop() override {}
  bool connected() const {
    for (const auto& message : messages)
      if (message.find("已连接到") != std::string::npos) return true;
    return false;
  }
};

Snapshot event(std::uint64_t id, std::uint64_t sequence, Stage stage) {
  Snapshot out{};
  out.transaction_id = id;
  out.sequence = sequence;
  out.stage = stage;
  return out;
}

void makeReady(Snapshot& value, unsigned a = 192, unsigned b = 0,
               unsigned c = 2, unsigned d = 9) {
  value.stage = Stage::IpReady;
  value.authenticated = true;
  value.dhcp_acquired = true;
  value.link_up = true;
  value.lease_held = true;
  value.operation_complete = true;
  value.ipv4[0] = static_cast<std::uint8_t>(a);
  value.ipv4[1] = static_cast<std::uint8_t>(b);
  value.ipv4[2] = static_cast<std::uint8_t>(c);
  value.ipv4[3] = static_cast<std::uint8_t>(d);
}

void enterCredentials(Controller& controller) {
  controller.start();
  controller.ingest("你好，openvela");
  controller.poll();
  controller.ingest("网络一");
  for (const char* token : {"a", "b", "c", "d", "一", "二", "三", "四"})
    controller.ingest(token);
  controller.ingest("完成");
  controller.ingest("确认提交");
}

int main() {
  ScanDelegate scan;
  FakeBackend backend;
  WifiTransactionAdapter adapter(scan, backend);

  const char fixture[] = "abcd1234";
  auto result = adapter.beginConnect("VoiceTest", fixture, 8);
  assert(result.status == ConnectStatus::CredentialsReceived);
  assert(result.request_id == 77);
  assert(result.ipv4.empty());
  assert(backend.copied_ssid == "VoiceTest");
  assert(backend.copied_password == std::vector<char>(fixture, fixture + 8));

  backend.next = event(77, 1, Stage::InProgress);
  result = adapter.pollConnect(77);
  assert(result.status == ConnectStatus::Connecting);
  backend.next = event(77, 2, Stage::Authenticated);
  backend.next.authenticated = true;
  result = adapter.pollConnect(77);
  assert(result.status == ConnectStatus::Connecting);
  assert(adapter.lastProgress().stage == Stage::Authenticated);
  backend.next = event(77, 3, Stage::Dhcp);
  backend.next.authenticated = true;
  result = adapter.pollConnect(77);
  assert(result.status == ConnectStatus::Connecting);

  // A delayed event for the same transaction cannot regress DHCP to accepted.
  backend.next = event(77, 1, Stage::Accepted);
  result = adapter.pollConnect(77);
  assert(result.status == ConnectStatus::Connecting);
  assert(adapter.lastProgress().stage == Stage::Dhcp);

  backend.next = event(77, 4, Stage::IpReady);
  backend.next.ipv4[0] = 192;
  backend.next.ipv4[1] = 0;
  backend.next.ipv4[2] = 2;
  backend.next.ipv4[3] = 9;
  result = adapter.pollConnect(77);
  assert(result.status == ConnectStatus::Failed);  // flags are mandatory

  backend.submit.transaction_id = 78;
  result = adapter.beginConnect("VoiceTest", fixture, 8);
  assert(result.status == ConnectStatus::CredentialsReceived);
  backend.next = event(78, 1, Stage::IpReady);
  makeReady(backend.next);
  result = adapter.pollConnect(78);
  assert(result.status == ConnectStatus::IpReady);
  assert(result.ipv4 == "192.0.2.9");

  for (const auto& item : {
           std::pair{FailureReason::Authentication, ConnectStatus::WrongPassword},
           std::pair{FailureReason::NetworkNotFound, ConnectStatus::NetworkNotFound},
           std::pair{FailureReason::UnsupportedSecurity, ConnectStatus::Unsupported},
           std::pair{FailureReason::Backend, ConnectStatus::Failed}}) {
    backend.submit.transaction_id++;
    const auto id = backend.submit.transaction_id;
    adapter.beginConnect("VoiceTest", fixture, 8);
    backend.next = event(id, 1, Stage::Failed);
    backend.next.failure_reason = item.first;
    result = adapter.pollConnect(id);
    assert(result.status == item.second);
  }

  backend.submit.transaction_id = 90;
  adapter.beginConnect("VoiceTest", fixture, 8);
  backend.next = event(90, 1, Stage::Timeout);
  assert(adapter.pollConnect(90).status == ConnectStatus::Timeout);

  backend.submit.transaction_id = 91;
  adapter.beginConnect("VoiceTest", fixture, 8);
  adapter.cancelConnect(91);
  adapter.cancelConnect(91);
  assert(backend.cancels == 1);
  backend.next = event(91, 1, Stage::IpReady);
  makeReady(backend.next);
  assert(adapter.pollConnect(91).status == ConnectStatus::Cancelled);

  // The backend can surface an old transaction. Its ID is never relabelled.
  backend.submit.transaction_id = 100;
  adapter.beginConnect("VoiceTest", fixture, 8);
  backend.next = event(99, 9, Stage::IpReady);
  makeReady(backend.next);
  result = adapter.pollConnect(100);
  assert(result.request_id == 99);
  assert(adapter.activeTransaction() == 100);
  backend.next = event(100, 1, Stage::IpReady);
  makeReady(backend.next);
  assert(adapter.pollConnect(100).status == ConnectStatus::IpReady);

  // Full Controller check: accepted/auth/DHCP never announces connection.
  FakeBackend flow_backend;
  flow_backend.submit.transaction_id = 701;
  WifiTransactionAdapter flow_adapter(scan, flow_backend);
  Clock clock;
  Speaker speaker;
  Controller controller(speaker, flow_adapter, clock);
  enterCredentials(controller);
  assert(controller.context().state == State::CredentialsReceived);
  assert(!speaker.connected());
  flow_backend.next = event(701, 1, Stage::Authenticated);
  flow_backend.next.authenticated = true;
  controller.poll();
  assert(controller.context().state == State::ConnectingWifi);
  assert(!speaker.connected());
  flow_backend.next = event(701, 2, Stage::Dhcp);
  flow_backend.next.authenticated = true;
  flow_backend.next.dhcp_acquired = true;
  controller.poll();
  assert(!speaker.connected());
  flow_backend.next = event(700, 99, Stage::IpReady);
  makeReady(flow_backend.next);
  controller.poll();
  assert(!speaker.connected());
  flow_backend.next = event(701, 3, Stage::IpReady);
  makeReady(flow_backend.next);
  controller.poll();
  assert(controller.context().state == State::Completed);
  assert(speaker.connected());

  std::cout << "wifi transaction adapter: 10 scenario groups passed; fake backend only\n";
}
