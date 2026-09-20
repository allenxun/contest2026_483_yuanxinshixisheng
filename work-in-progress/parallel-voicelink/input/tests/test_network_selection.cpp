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
  bool speak(const std::string& text) override {
    lines.push_back(text);
    return !fail;
  }
  void stop() override {}
  bool contains(const std::string& needle) const {
    for (auto& l : lines) if (l.find(needle) != std::string::npos) return true;
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

voicelink::ScanResult defaultAps() {
  voicelink::ScanResult r;
  r.status = voicelink::IoStatus::Ok;
  r.access_points = {
    {"weak", -80, true}, {"Home", -40, true}, {"Cafe", -50, false},
    {"Home", -60, true}, {"Office", -30, true}, {"", -70, true}
  };
  return r;
}

void testScanSortsDedupesAndCaps() {
  FakeTts tts; FakeWifi wifi; wifi.result = defaultAps();
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  CHECK(c.context().state == voicelink::State::WaitingNetworkChoice);
  CHECK(wifi.scans == 1);
  // Sorted by RSSI: Office(-30), Home(-40), Cafe(-50), weak(-80). Empty SSID removed.
  // Duplicate Home merged to strongest (-40).
  CHECK(c.context().candidates.size() == 4);
  CHECK(c.context().candidates[0].ssid == "Office");
  CHECK(c.context().candidates[0].rssi == -30);
  CHECK(c.context().candidates[1].ssid == "Home");
  CHECK(c.context().candidates[2].ssid == "Cafe");
  CHECK(c.context().candidates[2].secured == false);
  CHECK(c.context().candidates[3].ssid == "weak");
  // 问候语用 Config 默认值，避免文案微调时测试跟着改；但必须自报家门。
  CHECK(tts.lines[0] == voicelink::Config{}.greeting);
  CHECK(tts.lines[0].find("openvela") != std::string::npos);
}

void testMaxFiveNetworks() {
  FakeTts tts; FakeWifi wifi;
  wifi.result.status = voicelink::IoStatus::Ok;
  for (int i = 0; i < 8; ++i)
    wifi.result.access_points.push_back({"N" + std::to_string(i), -30 - i, true});
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  CHECK(c.context().candidates.size() == 5);
}

void testEmptyScanPromptsRescan() {
  FakeTts tts; FakeWifi wifi;
  wifi.result.status = voicelink::IoStatus::Ok;
  // Empty access_points = genuine scan with no networks found.
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  CHECK(c.context().state == voicelink::State::WaitingNetworkChoice);
  CHECK(tts.contains("没有发现网络"));
}

void testRescanRepeatsScan() {
  FakeTts tts; FakeWifi wifi; wifi.result = defaultAps();
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  int before = wifi.scans;
  c.ingest("重新扫描");
  CHECK(wifi.scans == before + 1);
  CHECK(c.context().state == voicelink::State::WaitingNetworkChoice);
  CHECK(c.context().password.empty());
}

void testInvalidIndexKeepsListening() {
  FakeTts tts; FakeWifi wifi; wifi.result = defaultAps();
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  c.ingest("网络九");
  CHECK(c.context().state == voicelink::State::WaitingNetworkChoice);
  CHECK(!c.context().selected_index.has_value());
  CHECK(tts.contains("编号无效"));
}

void testCancelClearsAndIdles() {
  FakeTts tts; FakeWifi wifi; wifi.result = defaultAps();
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  c.ingest("取消");
  CHECK(c.context().state == voicelink::State::Idle);
  CHECK(c.context().password.empty());
}

void testOpenNetworkSkipsPassword() {
  FakeTts tts; FakeWifi wifi; wifi.result = defaultAps();
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  c.ingest("网络三");
  CHECK(c.context().state == voicelink::State::Completed);
  CHECK(tts.contains("已连接"));
}

void testSecuredNetworkEntersPassword() {
  FakeTts tts; FakeWifi wifi; wifi.result = defaultAps();
  voicelink::Controller c(tts, wifi);
  c.start();
  c.ingest("openvela");
  c.ingest("网络一");
  CHECK(c.context().state == voicelink::State::EnteringPassword);
  CHECK(c.context().grammar == voicelink::Grammar::PasswordToken);
}

void testXiaoxinDoesNotWake() {
  // 「小信」及其带礼貌前缀的变体、以及只有前缀没有品牌名的输入都不能唤醒。
  for (const char* phrase : {"小信", "你好，小信", "hello", "你好", "xiaoxin"}) {
    FakeTts tts; FakeWifi wifi; wifi.result = defaultAps();
    voicelink::Controller c(tts, wifi);
    c.start();
    c.ingest(phrase);
    CHECK(c.context().state == voicelink::State::WaitingWake);
    CHECK(wifi.scans == 0);
    CHECK(tts.lines.empty());
  }
}

// 大赛统一唤醒词端到端：说「你好，openvela」/「Hello，openvela」必须唤醒并扫描。
void testContestWakePhrasesWake() {
  for (const char* phrase : {"你好，openvela", "Hello，openvela", "你好 openvela",
                             "hello, openvela", "您好，openvela", "openvela"}) {
    FakeTts tts; FakeWifi wifi; wifi.result = defaultAps();
    voicelink::Controller c(tts, wifi);
    c.start();
    c.ingest(phrase);
    CHECK(c.context().state == voicelink::State::WaitingNetworkChoice);
    CHECK(c.context().grammar == voicelink::Grammar::NetworkSelection);
    CHECK(wifi.scans == 1);
    CHECK(tts.contains("openvela"));
    CHECK(tts.contains("请选择网络"));
  }
}

}  // namespace

int main() {
  testScanSortsDedupesAndCaps();
  testMaxFiveNetworks();
  testEmptyScanPromptsRescan();
  testRescanRepeatsScan();
  testInvalidIndexKeepsListening();
  testCancelClearsAndIdles();
  testOpenNetworkSkipsPassword();
  testSecuredNetworkEntersPassword();
  testXiaoxinDoesNotWake();
  testContestWakePhrasesWake();
  if (failures) std::cerr << failures << " test(s) failed\n";
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}