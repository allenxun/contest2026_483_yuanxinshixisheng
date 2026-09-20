#include "voicelink/parsers.hpp"
#include "voicelink/types.hpp"

#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace {

int failures = 0;
#define CHECK(cond) do { if(!(cond)){ std::cerr<<__FILE__<<':'<<__LINE__<<" CHECK failed: " #cond "\n"; ++failures; } } while(0)

// 默认配置即大赛统一唤醒词：你好，openvela / Hello，openvela（外加裸 openvela）。
const std::vector<std::string>& configured = voicelink::defaultWakeWords();

// 大赛强制唤醒词必须唤醒，这是红线要求。
void testContestWakeWords() {
  CHECK(voicelink::isWakeWord("你好，openvela", configured));
  CHECK(voicelink::isWakeWord("Hello，openvela", configured));
  // ASR 实际会输出的各种形态：半角标点、空格、大小写、句末语气标点。
  CHECK(voicelink::isWakeWord("你好, openvela", configured));
  CHECK(voicelink::isWakeWord("你好openvela", configured));
  CHECK(voicelink::isWakeWord("你好openvela。", configured));
  CHECK(voicelink::isWakeWord("hello openvela", configured));
  CHECK(voicelink::isWakeWord("Hello, OpenVela!", configured));
  CHECK(voicelink::isWakeWord("HELLO，OPENVELA", configured));
  CHECK(voicelink::isWakeWord("  你好， open vela  ", configured));
  // 其他礼貌前缀同样接受，避免口音/用语差异导致唤不醒。
  CHECK(voicelink::isWakeWord("您好，openvela", configured));
  CHECK(voicelink::isWakeWord("嗨 openvela", configured));
  CHECK(voicelink::isWakeWord("嘿，openvela", configured));
  CHECK(voicelink::isWakeWord("hi, openvela", configured));
  CHECK(voicelink::isWakeWord("hey openvela", configured));
}
// 裸 openvela 的宽松匹配保持不变（调试与硬件侧既有 KWS 词表仍可用）。
void testBareWakeWords() {
  CHECK(voicelink::isWakeWord("openvela", configured));
  CHECK(voicelink::isWakeWord("Open Vela", configured));
  CHECK(voicelink::isWakeWord("OPEN-VELA", configured));
  CHECK(voicelink::isWakeWord(" openvela ", configured));
  CHECK(voicelink::isWakeWord("OPEN_VELA", configured));
  CHECK(voicelink::isWakeWord("open_vela", configured));
  CHECK(voicelink::isWakeWord("open-vela", configured));
  CHECK(voicelink::isWakeWord("Open，Vela。", configured));
  CHECK(voicelink::isWakeWord("OpenVela", configured));
}
void testNegativeWakeWords() {
  // 小信 must NOT wake — it is the explicit negative example.
  CHECK(!voicelink::isWakeWord("小信", configured));
  CHECK(!voicelink::isWakeWord("xiaoxin", configured));
  CHECK(!voicelink::isWakeWord("你好，小信", configured));
  CHECK(!voicelink::isWakeWord("Hello, xiaoxin", configured));
  // 品牌名不完整或多字，都不是唤醒词。
  CHECK(!voicelink::isWakeWord("openvela123", configured));
  CHECK(!voicelink::isWakeWord("open", configured));
  CHECK(!voicelink::isWakeWord("vela", configured));
  CHECK(!voicelink::isWakeWord("open velaa", configured));
  CHECK(!voicelink::isWakeWord("你好openvela你好", configured));
  // 只有礼貌前缀、没有品牌名时不能唤醒。
  CHECK(!voicelink::isWakeWord("hello", configured));
  CHECK(!voicelink::isWakeWord("你好", configured));
  CHECK(!voicelink::isWakeWord("你好，", configured));
  // 空输入与业务话术不能唤醒。
  CHECK(!voicelink::isWakeWord("", configured));
  CHECK(!voicelink::isWakeWord("   ", configured));
  CHECK(!voicelink::isWakeWord("，。！？", configured));
  CHECK(!voicelink::isWakeWord("请帮我配网", configured));
  CHECK(!voicelink::isWakeWord("网络一", configured));
}

// 单候选词重载与 vector 版本行为一致。
void testSinglePhraseOverload() {
  CHECK(voicelink::isWakeWord("你好，openvela", std::string("openvela")));
  CHECK(voicelink::isWakeWord("Hello，openvela", std::string("openvela")));
  CHECK(voicelink::isWakeWord("你好，openvela", std::string("你好openvela")));
  CHECK(voicelink::isWakeWord("Hello，openvela", std::string("Hello，openvela")));
  CHECK(!voicelink::isWakeWord("小信", std::string("openvela")));
  CHECK(!voicelink::isWakeWord("hello", std::string("openvela")));
}

void testCustomConfig() {
  // 只配置大赛短语时，裸 openvela 不放行（配置即语义，行为可预测）。
  const std::vector<std::string> contestOnly{"你好openvela", "helloopenvela"};
  CHECK(voicelink::isWakeWord("你好，openvela", contestOnly));
  CHECK(voicelink::isWakeWord("Hello，openvela", contestOnly));
  CHECK(!voicelink::isWakeWord("openvela", contestOnly));

  // 自定义唤醒词同样享受前缀剥离与标点折叠。
  const std::vector<std::string> custom{"openvela配网"};
  CHECK(voicelink::isWakeWord("你好，openvela 配网", custom));
  CHECK(!voicelink::isWakeWord("openvela", custom));

  // 空配置 / 含空串的配置不能唤醒，也不会崩。
  const std::vector<std::string> none{};
  CHECK(!voicelink::isWakeWord("你好，openvela", none));
  const std::vector<std::string> blanks{"", "  "};
  CHECK(!voicelink::isWakeWord("你好，openvela", blanks));
  CHECK(!voicelink::isWakeWord("", blanks));
  const std::vector<std::string> withBlank{"", "openvela"};
  CHECK(voicelink::isWakeWord("你好，openvela", withBlank));
  CHECK(!voicelink::isWakeWord("openvela", std::string("")));
}

// Config 默认值必须是大赛唤醒词，问候语要能自报家门。
void testConfigDefaults() {
  voicelink::Config cfg;
  CHECK(cfg.wake_words == voicelink::defaultWakeWords());
  CHECK(voicelink::isWakeWord("你好，openvela", cfg.wake_words));
  CHECK(voicelink::isWakeWord("Hello，openvela", cfg.wake_words));
  CHECK(!voicelink::isWakeWord("小信", cfg.wake_words));
  CHECK(cfg.greeting.find("openvela") != std::string::npos);
}

}  // namespace

int main() {
  testContestWakeWords();
  testBareWakeWords();
  testNegativeWakeWords();
  testSinglePhraseOverload();
  testCustomConfig();
  testConfigDefaults();
  if (failures) std::cerr << failures << " test(s) failed\n";
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
