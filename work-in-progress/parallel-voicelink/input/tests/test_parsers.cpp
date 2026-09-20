#include "voicelink/parsers.hpp"

#include <cstdlib>
#include <iostream>
#include <string>

namespace {

int failures = 0;
#define CHECK(cond) do { if(!(cond)){ std::cerr<<__FILE__<<':'<<__LINE__<<" CHECK failed: " #cond "\n"; ++failures; } } while(0)

void testAllUpperLetters() {
  for (char c = 'A'; c <= 'Z'; ++c) {
    std::string input = "upper_" + std::string(1, static_cast<char>(std::tolower(c)));
    auto t = voicelink::parsePasswordToken(input);
    CHECK(t.has_value());
    CHECK(t->character.has_value());
    CHECK(*t->character == c);
    CHECK(!t->control.has_value());
  }
}

void testAllLowerLetters() {
  for (char c = 'a'; c <= 'z'; ++c) {
    std::string input = "lower_" + std::string(1, static_cast<char>(std::toupper(c)));
    auto t = voicelink::parsePasswordToken(input);
    CHECK(t.has_value());
    CHECK(t->character.has_value());
    CHECK(*t->character == c);
    CHECK(!t->control.has_value());
  }
}

void testAllDigits() {
  const char* names[] = {"零","一","二","三","四","五","六","七","八","九"};
  for (int i = 0; i <= 9; ++i) {
    // digit_N form
    auto t1 = voicelink::parsePasswordToken("digit_" + std::to_string(i));
    CHECK(t1.has_value());
    CHECK(*t1->character == ('0' + i));
    // bare digit
    auto t2 = voicelink::parsePasswordToken(std::to_string(i));
    CHECK(t2.has_value());
    CHECK(*t2->character == ('0' + i));
    // Chinese digit
    auto t3 = voicelink::parsePasswordToken(names[i]);
    CHECK(t3.has_value());
    CHECK(*t3->character == ('0' + i));
    // 数字X form
    auto t4 = voicelink::parsePasswordToken(std::string("数字") + names[i]);
    CHECK(t4.has_value());
    CHECK(*t4->character == ('0' + i));
  }
}

void testSymbols() {
  struct Sym { std::string text; char expect; };
  Sym syms[] = {
    {"井号", '#'}, {"#", '#'},
    {"星号", '*'}, {"*", '*'},
    {"下划线", '_'}, {"_", '_'},
    {"横线", '-'}, {"减号", '-'}, {"-", '-'},
    {"感叹号", '!'}, {"!", '!'},
    {"艾特", '@'}, {"at", '@'}, {"@", '@'},
    {"点号", '.'}, {"点", '.'}, {".", '.'},
    {"美元符号", '$'}, {"$", '$'},
    {"百分号", '%'}, {"%", '%'},
    {"加号", '+'}, {"+", '+'},
  };
  for (const auto& s : syms) {
    auto t = voicelink::parsePasswordToken(s.text);
    CHECK(t.has_value());
    CHECK(*t->character == s.expect);
  }
}

void testControlWords() {
  struct Ctrl { std::string text; voicelink::PasswordControl expect; };
  Ctrl ctrls[] = {
    {"完成", voicelink::PasswordControl::Finish},
    {"输入完成", voicelink::PasswordControl::Finish},
    {"control_finish", voicelink::PasswordControl::Finish},
    {"删除", voicelink::PasswordControl::DeleteLast},
    {"删除一个", voicelink::PasswordControl::DeleteLast},
    {"退格", voicelink::PasswordControl::DeleteLast},
    {"清空", voicelink::PasswordControl::Clear},
    {"重新输入", voicelink::PasswordControl::Restart},
    {"重输", voicelink::PasswordControl::Restart},
    {"取消", voicelink::PasswordControl::Cancel},
    {"取消配网", voicelink::PasswordControl::Cancel},
    {"当前长度", voicelink::PasswordControl::ReportLength},
    {"重复当前长度", voicelink::PasswordControl::ReportLength},
    {"切换大写", voicelink::PasswordControl::SwitchUpper},
    {"切换小写", voicelink::PasswordControl::SwitchLower},
    {"大写模式", voicelink::PasswordControl::SwitchUpper},
    {"小写模式", voicelink::PasswordControl::SwitchLower},
  };
  for (const auto& c : ctrls) {
    auto t = voicelink::parsePasswordToken(c.text);
    CHECK(t.has_value());
    CHECK(t->control.has_value());
    CHECK(*t->control == c.expect);
    CHECK(!t->character.has_value());
  }
}

void testChineseLetterAliases() {
  for (char c = 'A'; c <= 'Z'; ++c) {
    auto t1 = voicelink::parsePasswordToken(std::string("大写") + c);
    CHECK(t1.has_value());
    CHECK(*t1->character == c);
    auto t2 = voicelink::parsePasswordToken(std::string("大写字母") + c);
    CHECK(t2.has_value());
    CHECK(*t2->character == c);
  }
  for (char c = 'a'; c <= 'z'; ++c) {
    auto t1 = voicelink::parsePasswordToken(std::string("小写") + c);
    CHECK(t1.has_value());
    CHECK(*t1->character == c);
    auto t2 = voicelink::parsePasswordToken(std::string("小写字母") + c);
    CHECK(t2.has_value());
    CHECK(*t2->character == c);
  }
}

void testNormalization() {
  // Whitespace and punctuation are removed; ASCII is lowercased.
  auto t = voicelink::parsePasswordToken("  大写  A。 ");
  CHECK(t.has_value());
  CHECK(*t->character == 'A');
  // openvela with spaces and mixed case normalizes
  CHECK(voicelink::isWakeWord(" OPEN-VELA ", "openvela"));
  CHECK(voicelink::isWakeWord("Open Vela", "openvela"));
  CHECK(voicelink::isWakeWord("open，vela。", "openvela"));
  // 大赛统一唤醒词：半角/全角标点都要能折叠掉
  CHECK(voicelink::isWakeWord("你好，openvela", voicelink::defaultWakeWords()));
  CHECK(voicelink::isWakeWord("Hello, openvela", voicelink::defaultWakeWords()));
}

void testUnknownText() {
  CHECK(!voicelink::parsePasswordToken("密码是hello"));
  CHECK(!voicelink::parsePasswordToken(""));
  CHECK(!voicelink::parsePasswordToken("   "));
  CHECK(!voicelink::parsePasswordToken("随便说一句"));
}

void testNetworkIndexParsing() {
  CHECK(voicelink::parseNetworkIndex("一") == 1);
  CHECK(voicelink::parseNetworkIndex("1") == 1);
  CHECK(voicelink::parseNetworkIndex("第一个") == 1);
  CHECK(voicelink::parseNetworkIndex("网络一") == 1);
  CHECK(voicelink::parseNetworkIndex("网络1") == 1);
  CHECK(voicelink::parseNetworkIndex("二") == 2);
  CHECK(voicelink::parseNetworkIndex("两") == 2);
  CHECK(voicelink::parseNetworkIndex("网络二") == 2);
  CHECK(voicelink::parseNetworkIndex(" 网络 二。") == 2);
  CHECK(voicelink::parseNetworkIndex("三") == 3);
  CHECK(voicelink::parseNetworkIndex("第四个") == 4);
  CHECK(voicelink::parseNetworkIndex("五") == 5);
  CHECK(voicelink::parseNetworkIndex("第五个") == 5);
  // Out of range / invalid
  CHECK(!voicelink::parseNetworkIndex("0"));
  CHECK(!voicelink::parseNetworkIndex("6"));
  CHECK(!voicelink::parseNetworkIndex("网络六"));
  CHECK(!voicelink::parseNetworkIndex("第六个"));
  CHECK(!voicelink::parseNetworkIndex(""));
  CHECK(!voicelink::parseNetworkIndex("蓝牙"));
  CHECK(!voicelink::parseNetworkIndex("随便"));
}

void testRescanAndCancel() {
  CHECK(voicelink::isRescan("重新扫描"));
  CHECK(voicelink::isRescan("再扫描"));
  CHECK(voicelink::isRescan("扫描网络"));
  CHECK(voicelink::isCancel("取消"));
  CHECK(voicelink::isCancel("取消配网"));
  CHECK(voicelink::isNetworkRestart("重新选择网络"));
  CHECK(voicelink::isNetworkRestart("重新配网"));
  CHECK(voicelink::isNetworkRestart("更换网络"));
  CHECK(voicelink::isNetworkRestart("重新扫描"));
}

}  // namespace

int main() {
  testAllUpperLetters();
  testAllLowerLetters();
  testAllDigits();
  testSymbols();
  testControlWords();
  testChineseLetterAliases();
  testNormalization();
  testUnknownText();
  testNetworkIndexParsing();
  testRescanAndCancel();
  if (failures) std::cerr << failures << " test(s) failed\n";
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}