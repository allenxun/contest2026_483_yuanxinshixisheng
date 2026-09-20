#include "voicelink/spoken_ssid.hpp"
#include "prompt_asset_output.hpp"

#include <cassert>
#include <cstring>
#include <string>
#include <vector>

namespace {
std::vector<std::string> played;
}

extern "C" int k7sound_speak_mono16(const std::int16_t* pcm, unsigned,
                                      unsigned) {
  for (const auto& asset : k7_prompt_assets::assets) {
    if (asset.pcm == pcm) {
      played.emplace_back(asset.key);
      return 0;
    }
  }
  return -1;
}

int main() {
  PromptAssetOutput output;
  assert(output.say("设备还没有联网，请联网。") == 0);
  assert((played == std::vector<std::string>{"wake"}));

  played.clear();
  assert(output.say("网络一，" + voicelink::spokenSsid("VoiceTest") + "。") == 0);
  const std::vector<std::string> expected{
      "network_1", "ssid_upper", "ssid_v", "ssid_o", "ssid_i", "ssid_c",
      "ssid_e", "ssid_upper", "ssid_t", "ssid_e", "ssid_s", "ssid_t"};
  assert(played == expected);

  played.clear();
  assert(output.say("网络二，" + voicelink::spokenSsid("小米") + "。") == 0);
  assert((played == std::vector<std::string>{"network_2", "ssid_nonascii"}));

  played.clear();
  assert(output.say("已选择VoiceTest，请逐个输入密码字符") == 0);
  assert((played == std::vector<std::string>{"selected"}));
  played.clear();
  assert(output.say("已连接到VoiceTest") == 0);
  assert((played == std::vector<std::string>{"connected"}));
}
