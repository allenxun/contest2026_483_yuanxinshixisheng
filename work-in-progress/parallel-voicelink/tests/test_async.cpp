#include "voicelink/controller.hpp"
#include <cstdlib>
#include <iostream>
#include <deque>
#include <stdexcept>
using namespace voicelink;
namespace {
int failures = 0, cases = 0;
#define CHECK(x) do { if (!(x)) { ++failures; std::cerr << __LINE__ << ": " #x "\n"; } } while (0)
struct Clock : ClockPort {
  std::uint64_t now{};
  std::uint64_t nowMs() const noexcept override { return now; }
};
struct Tts : TtsPort {
  std::vector<std::string> lines;
  bool fail{};
  bool throw_speak{}, throw_stop{};
  bool speak(const std::string& s) override {
    if (throw_speak) throw std::runtime_error("synthetic TTS failure");
    lines.push_back(s); return !fail;
  }
  void stop() override { if (throw_stop) throw std::runtime_error("synthetic stop failure"); }
  bool contains(const std::string& s) const {
    for (auto& line : lines) if (line.find(s) != std::string::npos) return true;
    return false;
  }
};
struct Wifi : WifiPort {
  std::uint64_t id{}, cancelled{};
  int begins{}, polls{};
  bool throw_scan{}, scan_fail{}, open{}, many{};
  ConnectStatus initial{ConnectStatus::CredentialsReceived};
  std::deque<ConnectResult> events;
  ScanResult scan() override {
    if (throw_scan) throw std::runtime_error("synthetic scan failure");
    if (scan_fail) return {IoStatus::FatalError, {}, -38};
    ScanResult r{IoStatus::Ok, {{"TestNet", -10, !open}}, 0};
    if (many) for (int i = 0; i < 10; ++i) r.access_points.push_back({"Extra" + std::to_string(i), -30-i, true});
    return r;
  }
  ConnectResult beginConnect(const std::string&, const char* p, std::size_t n) noexcept override {
    ++begins; ++id;
    CHECK(open ? (p == nullptr && n == 0) : (p && n == 8));
    // No credential storage in the mock. Synthetic IP is not hardware evidence.
    return {initial, 0, id, initial == ConnectStatus::IpReady ? "192.0.2.7" : ""};
  }
  ConnectResult pollConnect(std::uint64_t req) noexcept override {
    ++polls;
    if (events.empty()) return {ConnectStatus::CredentialsReceived, 0, req, {}};
    auto e = events.front(); events.pop_front(); return e;
  }
  void cancelConnect(std::uint64_t req) noexcept override { cancelled = req; }
};
struct Fixture {
  Tts t; Wifi w; Clock clock; Controller c;
  Fixture(Config config = {}) : c(t, w, clock, config) {}
  void select() { c.start(); c.ingest("hello openvela"); c.ingest("网络一"); }
  void submit() { for (int i = 0; i < 8; ++i) c.ingest("a"); c.ingest("完成"); }
  void event(ConnectStatus s, const std::string& ip = "") {
    w.events.push_back({s, 0, w.id, ip}); c.poll();
  }
};
void receiptToSuccess() {
  ++cases; Fixture f; f.select(); f.submit();
  CHECK(f.c.context().state == State::CredentialsReceived);
  CHECK(f.c.context().password.empty()); CHECK(!f.t.contains("已连接到"));
  f.c.ingest("完成"); CHECK(f.w.begins == 1);
  f.event(ConnectStatus::Connecting); CHECK(f.c.context().state == State::ConnectingWifi);
  f.event(ConnectStatus::CredentialsReceived); CHECK(f.c.context().state == State::ConnectingWifi);
  f.event(ConnectStatus::IpReady, "192.0.2.7"); CHECK(f.c.context().state == State::Completed);
  CHECK(f.t.contains("已连接到")); CHECK(!f.t.contains("aaaaaaaa"));
  f.c.poll(); CHECK(f.w.polls == 3); CHECK(f.w.cancelled == 0);
}
void failurePaths() {
  for (auto status : {ConnectStatus::WrongPassword, ConnectStatus::Timeout,
       ConnectStatus::NetworkNotFound, ConnectStatus::Failed, ConnectStatus::Busy,
       ConnectStatus::Unsupported, ConnectStatus::Cancelled}) {
    ++cases; Fixture f; f.select(); f.submit(); f.event(status);
    CHECK(f.c.context().state == (status == ConnectStatus::Cancelled ? State::Idle : State::EnteringPassword));
    CHECK(f.w.cancelled == 1); CHECK(f.c.context().password.empty());
    CHECK(!f.t.contains("已连接到"));
  }
}
void invalidIps() {
  for (auto ip : {"", "0.0.0.0", "127.0.0.1", "169.254.1.2", "224.0.0.1", "255.255.255.255",
                 "192.0.2", "192.0.2.999", "192.0.2.1junk", "192.0.2.1.2"}) {
    ++cases; Fixture f; f.select(); f.submit(); f.event(ConnectStatus::IpReady, ip);
    CHECK(f.c.context().state == State::EnteringPassword); CHECK(!f.t.contains("已连接到"));
  }
}
void timeoutAndStale() {
  ++cases; Fixture f; f.select(); f.submit();
  f.w.events.push_back({ConnectStatus::IpReady, 0, 999, "192.0.2.7"}); f.c.poll();
  CHECK(f.c.context().state == State::CredentialsReceived);
  f.clock.now = 29999; f.c.poll(); CHECK(f.w.cancelled == 0);
  f.w.events.push_back({ConnectStatus::IpReady, 0, 1, "192.0.2.7"});
  f.clock.now = 30000; f.c.poll(); CHECK(f.w.cancelled == 1);
  CHECK(f.t.contains("连接超时")); CHECK(!f.t.contains("已连接到"));
  f.submit(); CHECK(f.w.id == 2); f.c.poll(); // previous success cannot complete retry
  CHECK(f.c.context().state == State::CredentialsReceived);
  f.event(ConnectStatus::IpReady, "192.0.2.8"); CHECK(f.c.context().state == State::Completed);
}
void cleanup() {
  for (int action = 0; action < 6; ++action) {
    ++cases; Fixture f; f.select(); f.submit();
    switch (action) {
      case 0: f.c.ingest("取消"); break;
      case 1: f.c.resetToWake(); break;
      case 2: CHECK(!f.c.handleInputStatus(IoStatus::EndOfInput)); break;
      case 3: CHECK(!f.c.handleInputStatus(IoStatus::FatalError)); break;
      case 4: f.t.fail = true; f.event(ConnectStatus::Connecting); break;
      case 5: f.t.fail = true; CHECK(!f.c.handleInputStatus(IoStatus::RetryableError)); break;
    }
    CHECK(f.w.cancelled == 1); CHECK(f.c.context().password.empty());
    auto n = f.w.polls; f.c.poll(); CHECK(f.w.polls == n);
  }
  ++cases; Tts t; Wifi w; Clock clock;
  { Controller c(t, w, clock); c.start(); c.ingest("openvela"); c.ingest("网络一");
    for (int i = 0; i < 8; ++i) { c.ingest("a"); }
    c.ingest("完成"); }
  CHECK(w.cancelled == 1);
}
void otherPaths() {
  ++cases; Fixture f; f.w.open = true; f.w.initial = ConnectStatus::Unsupported; f.select();
  CHECK(f.c.context().state == State::WaitingNetworkChoice); CHECK(f.t.contains("暂不支持"));
  ++cases; Fixture busy; busy.w.initial = ConnectStatus::Busy; busy.select(); busy.submit();
  CHECK(busy.t.contains("网络服务忙")); CHECK(!busy.t.contains("已连接到"));
  ++cases; Fixture immediate; immediate.w.initial = ConnectStatus::IpReady; immediate.select(); immediate.submit();
  CHECK(immediate.c.context().state == State::Completed);
  for (bool throwing : {false, true}) {
    ++cases; Fixture bad; bad.w.scan_fail = !throwing; bad.w.throw_scan = throwing; bad.select();
    CHECK(bad.c.context().state == State::Error); CHECK(!bad.t.contains("没有发现网络"));
  }
  ++cases; Config cfg; cfg.max_networks = 20; Fixture many(cfg); many.w.many = true; many.select();
  CHECK(many.c.context().candidates.size() == 5);
  ++cases; Fixture pw; pw.select(); pw.c.ingest("切换大写"); pw.c.ingest("a");
  CHECK(pw.c.context().password[0] == 'A'); pw.c.ingest("删除"); CHECK(pw.c.context().password.empty());
  pw.c.ingest("b"); pw.c.ingest("清空"); pw.c.ingest("a"); CHECK(pw.c.context().password[0] == 'a');
  pw.t.fail = true; pw.c.ingest("b"); CHECK(pw.c.context().password.empty());
  CHECK(pw.c.context().state == State::Error);
}
void ttsExceptions() {
  for (int stage = 0; stage < 4; ++stage) {
    for (bool on_stop : {false, true}) {
      ++cases; Fixture f;
      if (stage >= 1) f.select();
      if (stage == 1) f.c.ingest("a");
      if (stage >= 2) f.submit();
      f.t.throw_stop = on_stop; f.t.throw_speak = !on_stop;
      if (stage == 0) f.c.ingest("openvela");
      if (stage == 1) f.c.ingest("b");
      if (stage == 2) f.event(ConnectStatus::Connecting);
      if (stage == 3) f.c.cancel();
      CHECK(f.c.context().state == State::Error);
      CHECK(f.c.context().password.empty());
      if (stage >= 2) CHECK(f.w.cancelled == 1);
    }
  }
  ++cases; Fixture f; f.select(); f.submit(); f.t.throw_stop = true;
  f.c.resetToWake(); CHECK(f.c.context().state == State::Error); CHECK(f.w.cancelled == 1);
}
}
int main() {
  receiptToSuccess(); failurePaths(); invalidIps(); timeoutAndStale(); cleanup(); otherPaths(); ttsExceptions();
  std::cout << "async cases=" << cases << " failures=" << ::failures << "\n";
  return ::failures ? EXIT_FAILURE : EXIT_SUCCESS;
}
