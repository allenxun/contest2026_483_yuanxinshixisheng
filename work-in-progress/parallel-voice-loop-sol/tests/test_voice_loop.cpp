#include "voice_loop.hpp"

#include <deque>
#include <iostream>
#include <stdexcept>
#include <utility>
#include <vector>

using namespace voice_loop;
using namespace voicelink;

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) throw std::runtime_error(#x); } while (0)

struct Clock final : ClockPort {
  std::uint64_t now{};
  std::uint64_t nowMs() const noexcept override { return now; }
};

struct Tts final : TtsPort {
  std::vector<std::string> prompts;
  bool speak(const std::string& s) override { prompts.push_back(s); return true; }
  void stop() override {}
  bool contains(const std::string& secret) const {
    for (const auto& p : prompts) if (p.find(secret) != std::string::npos) return true;
    return false;
  }
};

struct Capture final : CapturePort {
  std::uint64_t next{1};
  bool hold{};
  unsigned cancels{}, releases{}, begins{};
  std::vector<Grammar> grammars;
  CaptureResult begin(Grammar grammar) noexcept override {
    ++begins; grammars.push_back(grammar);
    const auto id = next++;
    return {hold ? CaptureStatus::Recording : CaptureStatus::Complete, id, 0};
  }
  CaptureResult poll(std::uint64_t id) noexcept override {
    return {hold ? CaptureStatus::Recording : CaptureStatus::Complete, id, 0};
  }
  void cancel(std::uint64_t) noexcept override { ++cancels; }
  void release(std::uint64_t) noexcept override { ++releases; }
};

struct Asr final : AsrPort {
  std::uint64_t next{100};
  std::deque<std::string> texts;
  bool hold{}, stale_once{};
  std::uint64_t active{};
  unsigned cancels{}, begins{};
  AsrResult begin(std::uint64_t, Grammar) noexcept override {
    ++begins; active = next++;
    if (hold) return {AsrStatus::Recognizing, active, 0, {}};
    std::string text;
    if (!texts.empty()) { text = std::move(texts.front()); texts.pop_front(); }
    return {AsrStatus::Ready, active, 0, std::move(text)};
  }
  AsrResult poll(std::uint64_t id) noexcept override {
    if (stale_once) { stale_once = false; return {AsrStatus::Ready, id + 999, 0, "旧事务"}; }
    if (hold) return {AsrStatus::Recognizing, id, 0, {}};
    std::string text;
    if (!texts.empty()) { text = std::move(texts.front()); texts.pop_front(); }
    return {AsrStatus::Ready, id, 0, std::move(text)};
  }
  void cancel(std::uint64_t) noexcept override { ++cancels; }
};

struct Wifi final : WifiPort {
  std::vector<AccessPoint> aps{{"SecureNet", -20, true}, {"Guest", -30, false}};
  ScanStatus scan_terminal{ScanStatus::Ready};
  ConnectStatus connect_terminal{ConnectStatus::IpReady};
  std::uint64_t scan_id{500}, connect_id{900};
  unsigned scan_polls{}, connect_polls{}, connect_begins{}, scan_cancels{}, connect_cancels{};
  std::string observed_password;
  bool stale_connect_once{};
  ScanResult beginScan() override { ++scan_id; scan_polls = 0; return {ScanStatus::Received, {}, 0, scan_id}; }
  ScanResult pollScan(std::uint64_t id) override {
    ++scan_polls;
    return scan_terminal == ScanStatus::Ready ? ScanResult{ScanStatus::Ready, aps, 0, id}
                                               : ScanResult{scan_terminal, {}, -10, id};
  }
  void cancelScan(std::uint64_t) noexcept override { ++scan_cancels; }
  ConnectResult beginConnect(const std::string&, const char* p, std::size_t n) noexcept override {
    ++connect_begins; ++connect_id; connect_polls = 0;
    observed_password.assign(p ? p : "", n);
    return {ConnectStatus::CredentialsReceived, 0, connect_id, {}};
  }
  ConnectResult pollConnect(std::uint64_t id) noexcept override {
    if (stale_connect_once) { stale_connect_once = false; return {ConnectStatus::IpReady, 0, id + 7, "10.0.0.7"}; }
    ++connect_polls;
    if (connect_polls == 1) return {ConnectStatus::Connecting, 0, id, {}};
    return {connect_terminal, -20, id, connect_terminal == ConnectStatus::IpReady ? "10.0.0.8" : ""};
  }
  void cancelConnect(std::uint64_t) noexcept override { ++connect_cancels; observed_password.clear(); }
};

struct Rig {
  Clock clock; Tts tts; Wifi wifi; Capture capture; Asr asr;
  Controller controller;
  Loop loop;
  Rig(voice_loop::Config loop_config = {}, voicelink::Config controller_config = {})
      : controller(tts, wifi, clock, std::move(controller_config)),
        loop(controller, capture, asr, clock, loop_config) {}
  void tick(unsigned count = 1, std::uint64_t advance = 1) {
    while (count--) { clock.now += advance; loop.tick(); }
  }
  void readyForSpeech() {
    for (unsigned i = 0; i < 20 && loop.phase() != Phase::WaitingPort; ++i) tick();
    CHECK(loop.phase() == Phase::WaitingPort);
  }
  void say(const std::string& text) {
    const auto before = loop.turn(); asr.texts.push_back(text);
    for (unsigned i = 0; i < 30 && loop.turn() == before; ++i) tick();
    CHECK(loop.turn() == before + 1);
  }
};

static void enterPassword(Rig& r) {
  CHECK(r.loop.start()); r.say("你好 openvela"); r.say("网络一");
  for (const char* token : {"a", "b", "c", "d", "一", "二", "三", "四"}) r.say(token);
  CHECK(r.controller.context().password.size() == 8);
  r.say("完成");
  CHECK(r.controller.context().state == State::ConfirmingPassword);
}

static void securedSuccess() {
  Rig r; enterPassword(r);
  CHECK(r.wifi.connect_begins == 0); r.say("继续"); CHECK(r.wifi.connect_begins == 0);
  r.say("确认提交"); CHECK(r.wifi.connect_begins == 1);
  CHECK(r.wifi.observed_password == "abcd1234");
  CHECK(r.controller.context().password.empty());
  r.tick(3); CHECK(r.loop.phase() == Phase::Completed);
  CHECK(!r.tts.contains("abcd1234"));
}

static void openNetwork() {
  Rig r; r.wifi.aps = {{"Cafe", -10, false}};
  CHECK(r.loop.start()); r.say("你好 openvela"); r.say("网络一");
  CHECK(r.controller.context().state == State::ConfirmingPassword);
  CHECK(r.wifi.connect_begins == 0); r.say("确认提交");
  CHECK(r.wifi.connect_begins == 1 && r.wifi.observed_password.empty());
  r.tick(3); CHECK(r.loop.phase() == Phase::Completed);
}

static void scanFailureAndCancel() {
  Rig r; r.wifi.scan_terminal = ScanStatus::Failed;
  CHECK(r.loop.start()); r.say("你好 openvela"); r.tick();
  CHECK(r.loop.phase() == Phase::Error && r.wifi.scan_cancels == 1);
  Rig c; CHECK(c.loop.start()); c.asr.hold = true; c.readyForSpeech(); c.tick();
  CHECK(c.loop.phase() == Phase::Recognizing); c.loop.cancel();
  CHECK(c.asr.cancels == 1 && c.capture.releases == 1 && c.loop.phase() == Phase::Idle);
  Rig s; CHECK(s.loop.start()); s.say("你好 openvela"); CHECK(s.loop.phase() == Phase::ControllerWork);
  s.loop.cancel(); CHECK(s.wifi.scan_cancels == 1 && s.loop.phase() == Phase::Idle);
}

static void timeoutsAndClock() {
  Rig r({5, 7, 1, 512}); r.capture.hold = true;
  CHECK(r.loop.start()); r.readyForSpeech(); r.tick(); CHECK(r.loop.phase() == Phase::Recording);
  r.tick(1, 5); CHECK(r.capture.cancels == 1); CHECK(r.loop.phase() == Phase::WaitingPort);
  Rig a({20, 5, 1, 512}); a.asr.hold = true;
  CHECK(a.loop.start()); a.readyForSpeech(); a.tick(); CHECK(a.loop.phase() == Phase::Recognizing);
  a.tick(1, 5); CHECK(a.asr.cancels == 1 && a.capture.releases == 1);
  Rig c; c.capture.hold = true; CHECK(c.loop.start()); c.readyForSpeech(); c.tick(); c.clock.now = 0; c.loop.tick();
  CHECK(c.loop.phase() == Phase::Error);
}

static void controllerTimeouts() {
  voicelink::Config scan_config; scan_config.scan_timeout_ms = 5;
  Rig scan({}, scan_config); CHECK(scan.loop.start()); scan.say("你好 openvela");
  scan.tick(1, 5); CHECK(scan.wifi.scan_cancels == 1 && scan.loop.phase() == Phase::Idle);

  voicelink::Config connect_config; connect_config.connect_timeout_ms = 5;
  Rig connect({}, connect_config); enterPassword(connect); connect.say("确认提交");
  connect.tick(1, 5);
  CHECK(connect.wifi.connect_cancels == 1);
  CHECK(connect.controller.context().state == State::EnteringPassword);
  CHECK(connect.loop.phase() == Phase::WaitingPort);
}

static void staleAndConnectionFailure() {
  Rig r; r.asr.hold = true; r.asr.stale_once = true;
  CHECK(r.loop.start()); r.readyForSpeech(); r.tick(); CHECK(r.loop.phase() == Phase::Recognizing);
  r.asr.texts.push_back("你好 openvela"); r.asr.hold = false;
  r.tick(); CHECK(r.loop.turn() == 0); r.tick(); CHECK(r.loop.turn() == 1);
  Rig f; enterPassword(f); f.wifi.connect_terminal = ConnectStatus::WrongPassword;
  f.wifi.stale_connect_once = true; f.say("确认提交");
  f.tick(); CHECK(f.controller.context().state == State::CredentialsReceived);
  f.tick(); CHECK(f.controller.context().state == State::ConnectingWifi);
  f.tick(); CHECK(f.controller.context().state == State::EnteringPassword);
  CHECK(f.wifi.connect_cancels == 1 && f.controller.context().password.empty());
}

static void invalidTextAndEnd() {
  Rig r({20, 20, 1, 8}); CHECK(r.loop.start()); r.asr.texts.push_back("文本内容超过限制");
  r.readyForSpeech(); r.tick(); CHECK(r.loop.turn() == 0 && r.loop.phase() == Phase::WaitingPort);
  CHECK(!r.tts.prompts.empty());
}

int main() {
  try {
    securedSuccess(); openNetwork(); scanFailureAndCancel(); timeoutsAndClock(); controllerTimeouts();
    staleAndConnectionFailure(); invalidTextAndEnd();
    std::cout << "voice_loop_checks=" << checks
              << " scenarios=9 failures=0 secrets_in_output=0\n";
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "failure=" << e.what() << "\n";
    return 1;
  }
}
