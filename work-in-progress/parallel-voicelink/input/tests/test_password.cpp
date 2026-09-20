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
  bool speak(const std::string& text) override { lines.push_back(text); return true; }
  void stop() override {}
  bool contains(const std::string& n) const {
    for (auto& l : lines) if (l.find(n) != std::string::npos) return true;
    return false;
  }
};

struct FakeWifi final : voicelink::WifiPort {
  voicelink::ScanResult scan() override {
    voicelink::ScanResult r;
    r.status = voicelink::IoStatus::Ok;
    r.access_points = {{"OfficeNet", -35, true}, {"Cafe", -50, false}};
    return r;
  }
  voicelink::ConnectStatus connect_status = voicelink::ConnectStatus::Ok;
  int connects = 0;
  voicelink::ConnectResult connect(const std::string&, const char*,
                                   std::size_t) override {
    ++connects;
    voicelink::ConnectResult r;
    r.status = connect_status;
    return r;
  }
};

void enterChar(voicelink::Controller& c, char ch) {
  if (ch >= 'A' && ch <= 'Z') c.ingest(std::string("大写") + ch);
  else if (ch >= 'a' && ch <= 'z') c.ingest(std::string(1, ch)); /* bare = lowercase by default */
  else if (ch >= '0' && ch <= '9') c.ingest(std::string(1, ch));
  else if (ch == '@') c.ingest("艾特");
  else if (ch == '#') c.ingest("井号");
  else if (ch == '!') c.ingest("感叹号");
}

void enterPassword(voicelink::Controller& c, const std::string& pw) {
  for (char ch : pw) enterChar(c, ch);
  c.ingest("完成");
}

void startAndSelect(voicelink::Controller& c) {
  c.start();
  c.ingest("openvela");
  c.ingest("网络一");  // OfficeNet, secured
}

void testAppendDeleteClearRestartLength() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  /* Bare letters default to lowercase */
  c.ingest("a");
  c.ingest("b");
  CHECK(c.context().password.size() == 2);
  CHECK(c.context().password[0] == 'a');
  CHECK(c.context().password[1] == 'b');
  c.ingest("当前长度");
  CHECK(tts.contains("当前长度为2"));
  c.ingest("删除");
  CHECK(c.context().password.size() == 1);
  c.ingest("清空");
  CHECK(c.context().password.empty());
  c.ingest("a");
  c.ingest("重输");
  CHECK(c.context().state == voicelink::State::EnteringPassword);
  CHECK(c.context().password.empty());
}

void testShortPasswordCannotFinish() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  for (int i = 0; i < 7; ++i) c.ingest("a");
  c.ingest("完成");
  CHECK(c.context().state == voicelink::State::EnteringPassword);
  CHECK(c.context().password.size() == 7);
  CHECK(tts.contains("长度不足"));
}

void testCannotAppendBeyondMax() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Config cfg;
  cfg.max_password_length = 63;
  voicelink::Controller c(tts, wifi, cfg);
  startAndSelect(c);
  for (int i = 0; i < 63; ++i) c.ingest("a");
  c.ingest("b");
  CHECK(c.context().password.size() == 63);
  CHECK(tts.contains("最大长度"));
}

void testFinishOnceConnects() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  enterPassword(c, "aaaaaaaa");
  CHECK(c.context().state == voicelink::State::Completed);
  CHECK(wifi.connects == 1);
  CHECK(tts.contains("已连接"));
}

void testWrongPasswordPromptsReenter() {
  FakeTts tts; FakeWifi wifi;
  wifi.connect_status = voicelink::ConnectStatus::WrongPassword;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  enterPassword(c, "aaaaaaaa");
  CHECK(c.context().state == voicelink::State::EnteringPassword);
  CHECK(c.context().password.empty());
  CHECK(tts.contains("密码错误"));
}

void testConnectTimeoutPromptsReenter() {
  FakeTts tts; FakeWifi wifi;
  wifi.connect_status = voicelink::ConnectStatus::Timeout;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  enterPassword(c, "aaaaaaaa");
  CHECK(c.context().state == voicelink::State::EnteringPassword);
  CHECK(tts.contains("连接超时"));
}

void testMatchingPasswordConnects() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  enterPassword(c, "aaaaaaaa");
  CHECK(c.context().state == voicelink::State::Completed);
  CHECK(c.context().password.empty());
  CHECK(tts.contains("已连接到"));
}

void testUnknownTokenDoesNotChangeBuffer() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  c.ingest("a");
  c.ingest("这不是字符");
  CHECK(c.context().password.size() == 1);
  CHECK(tts.contains("没有听清"));
}

void testCancelDuringPasswordClears() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  c.ingest("a");
  c.ingest("取消");
  CHECK(c.context().state == voicelink::State::Idle);
  CHECK(c.context().password.empty());
}

void testReselectNetworkDuringPassword() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  c.ingest("a");
  c.ingest("重新选择网络");
  CHECK(c.context().state == voicelink::State::WaitingNetworkChoice);
  CHECK(c.context().password.empty());
}

void testWrongCharDeleteThenFinish() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  for (int i = 0; i < 7; ++i) c.ingest("a");
  c.ingest("z");
  c.ingest("删除");
  c.ingest("a");
  c.ingest("完成");
  CHECK(c.context().state == voicelink::State::Completed);
}

void testToggleUpperCaseMode() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  /* Default lowercase */
  c.ingest("a");
  CHECK(c.context().password[0] == 'a');
  /* Switch to uppercase mode */
  c.ingest("切换大写");
  c.ingest("b");
  CHECK(c.context().password[1] == 'B');
  /* Explicit lowercase prefix still works */
  c.ingest("小写c");
  CHECK(c.context().password[2] == 'c');
  /* Switch back to lowercase mode */
  c.ingest("切换小写");
  c.ingest("d");
  CHECK(c.context().password[3] == 'd');
  /* Explicit uppercase prefix still works */
  c.ingest("大写e");
  CHECK(c.context().password[4] == 'E');
  CHECK(c.context().password.size() == 5);
}

void testModeResetsOnClear() {
  FakeTts tts; FakeWifi wifi;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  c.ingest("切换大写");
  c.ingest("a");
  CHECK(c.context().password[0] == 'A');
  c.ingest("清空");
  /* Mode should reset to lowercase */
  c.ingest("a");
  CHECK(c.context().password[0] == 'a');
}

void testModeResetsOnFailedConnect() {
  FakeTts tts; FakeWifi wifi;
  wifi.connect_status = voicelink::ConnectStatus::WrongPassword;
  voicelink::Controller c(tts, wifi);
  startAndSelect(c);
  c.ingest("切换大写");
  enterPassword(c, "aaaaaaaa");
  /* After wrong password, mode resets to lowercase */
  CHECK(c.context().password_mode == voicelink::PasswordMode::Lower);
  c.ingest("a");
  CHECK(c.context().password[0] == 'a');
}

}  // namespace

int main() {
  testAppendDeleteClearRestartLength();
  testShortPasswordCannotFinish();
  testCannotAppendBeyondMax();
  testFinishOnceConnects();
  testWrongPasswordPromptsReenter();
  testConnectTimeoutPromptsReenter();
  testMatchingPasswordConnects();
  testUnknownTokenDoesNotChangeBuffer();
  testCancelDuringPasswordClears();
  testReselectNetworkDuringPassword();
  testWrongCharDeleteThenFinish();
  testToggleUpperCaseMode();
  testModeResetsOnClear();
  testModeResetsOnFailedConnect();
  if (failures) std::cerr << failures << " test(s) failed\n";
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}