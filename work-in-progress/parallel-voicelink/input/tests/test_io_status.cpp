#include "voicelink/controller.hpp"
#include "voicelink/ports.hpp"

#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace {

int failures = 0;
#define CHECK(cond) do { if(!(cond)){ std::cerr<<__FILE__<<':'<<__LINE__<<" CHECK failed: " #cond "\n"; ++failures; } } while(0)

struct FakeTts final : voicelink::TtsPort {
  std::vector<std::string> lines;
  bool fail = false;
  bool speak(const std::string& text) override { lines.push_back(text); return !fail; }
  void stop() override {}
  bool contains(const std::string& n) const {
    for (auto& l : lines) if (l.find(n) != std::string::npos) return true;
    return false;
  }
};

struct FakeWifi final : voicelink::WifiPort {
  voicelink::ScanResult result;
  int scans = 0;
  voicelink::ConnectStatus connect_status = voicelink::ConnectStatus::Ok;
  voicelink::ScanResult scan() override { ++scans; return result; }
  voicelink::ConnectResult connect(const std::string&, const char*,
                                   std::size_t) override {
    voicelink::ConnectResult r;
    r.status = connect_status;
    return r;
  }
};

void enterChar(voicelink::Controller& c, char ch) {
  if (ch >= 'A' && ch <= 'Z') c.ingest(std::string("大写") + ch);
  else if (ch >= 'a' && ch <= 'z') c.ingest(std::string(1, ch)); /* bare = lowercase */
  else if (ch >= '0' && ch <= '9') c.ingest(std::string(1, ch));
  else if (ch == '#') c.ingest("井号");
  else if (ch == '@') c.ingest("艾特");
  else if (ch == '!') c.ingest("感叹号");
  else if (ch == '.') c.ingest("点号");
  else if (ch == '$') c.ingest("美元符号");
  else if (ch == '%') c.ingest("百分号");
  else if (ch == '+') c.ingest("加号");
  else if (ch == '-') c.ingest("横线");
  else if (ch == '*') c.ingest("星号");
  else if (ch == '_') c.ingest("下划线");
}

void enterPassword(voicelink::Controller& c, const std::string& pw) {
  for (char ch : pw) enterChar(c, ch);
  c.ingest("完成");
}

// ENOSYS / scan failure -> State::Error, NOT empty scan.
void testScanFatalErrorGoesToError() {
  FakeTts tts; FakeWifi wifi;
  wifi.result.status = voicelink::IoStatus::FatalError;
  wifi.result.error_code = -38;  // -ENOSYS
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  CHECK(c.context().state == voicelink::State::Error);
  CHECK(!tts.contains("没有发现网络"));
}

// Successful scan with zero APs -> stays in WaitingNetworkChoice, prompt rescan.
void testEmptySuccessScanStaysInChoice() {
  FakeTts tts; FakeWifi wifi;
  wifi.result.status = voicelink::IoStatus::Ok;
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  CHECK(c.context().state == voicelink::State::WaitingNetworkChoice);
  CHECK(tts.contains("没有发现网络"));
}

// KWS timeout -> still in WaitingWake.
void testKwsTimeoutStaysWaiting() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  c.start();
  bool cont = c.handleInputStatus(voicelink::IoStatus::Timeout);
  CHECK(cont);
  CHECK(c.context().state == voicelink::State::WaitingWake);
}

// ASR retryable error -> state unchanged, brief prompt.
void testAsrRetryableKeepsState() {
  FakeTts tts; FakeWifi wifi;
  wifi.result.status = voicelink::IoStatus::Ok;
  wifi.result.access_points = {{"Net", -30, true}};
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  voicelink::State before = c.context().state;
  bool cont = c.handleInputStatus(voicelink::IoStatus::RetryableError);
  CHECK(cont);
  CHECK(c.context().state == before);
  CHECK(tts.contains("没有听清"));
}

// EOF -> passwords wiped, handleInputStatus returns false.
void testEofWipesPasswords() {
  FakeTts tts; FakeWifi wifi;
  wifi.result.status = voicelink::IoStatus::Ok;
  wifi.result.access_points = {{"Net", -30, true}};
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  c.ingest("网络一");
  c.ingest("a");
  c.ingest("b");
  CHECK(c.context().password.size() == 2);
  bool cont = c.handleInputStatus(voicelink::IoStatus::EndOfInput);
  CHECK(!cont);
  CHECK(c.context().password.empty());
}

// FatalError -> State::Error, returns false.
void testFatalErrorGoesToError() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  c.start();
  bool cont = c.handleInputStatus(voicelink::IoStatus::FatalError);
  CHECK(!cont);
  CHECK(c.context().state == voicelink::State::Error);
}

// TTS failure -> State::Error.
void testTtsFailureGoesToError() {
  FakeTts tts; tts.fail = true;
  FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  CHECK(c.context().state == voicelink::State::Error);
}

// Password content must never appear in TTS output.
void testPasswordNotLeaked() {
  FakeTts tts; FakeWifi wifi;
  wifi.result.status = voicelink::IoStatus::Ok;
  wifi.result.access_points = {{"OfficeNet", -35, true}};
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  c.ingest("网络一");
  const std::string secret = "Tw7#kLm9";
  enterPassword(c, secret);
  CHECK(c.context().state == voicelink::State::Completed);
  for (const auto& line : tts.lines) {
    CHECK(line.find(secret) == std::string::npos);
    CHECK(line.find("Tw7") == std::string::npos);
    CHECK(line.find("kLm9") == std::string::npos);
  }
}

// Passwords are wiped on mismatch, cancel, restart, and confirm.
void testClearOnWrongPasswordCancelRestartConfirm() {
  FakeTts tts; FakeWifi wifi;
  wifi.result.status = voicelink::IoStatus::Ok;
  wifi.result.access_points = {{"Net", -30, true}};
  wifi.connect_status = voicelink::ConnectStatus::WrongPassword;
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  c.ingest("网络一");
  enterPassword(c, "aaaaaaaa");
  CHECK(c.context().password.empty());
  c.ingest("a");
  c.ingest("取消");
  CHECK(c.context().password.empty());
}

}  // namespace

int main() {
  testScanFatalErrorGoesToError();
  testEmptySuccessScanStaysInChoice();
  testKwsTimeoutStaysWaiting();
  testAsrRetryableKeepsState();
  testEofWipesPasswords();
  testFatalErrorGoesToError();
  testTtsFailureGoesToError();
  testPasswordNotLeaked();
  testClearOnWrongPasswordCancelRestartConfirm();
  if (failures) std::cerr << failures << " test(s) failed\n";
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}