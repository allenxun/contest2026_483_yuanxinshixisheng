#pragma once

#include "generated/k7_prompt_assets_generated.hpp"
#include "k7sound_api.h"

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <string>

// Fixed provisioning speech generated on the development PC.  The board keeps
// no TTS model/session and allocates no playback buffer from the system heap.
class PromptAssetOutput {
 public:
  int say(const std::string& text, unsigned capture_frames = 0) noexcept {
    if (starts(text, "网络一") || starts(text, "网络二") ||
        starts(text, "网络三") || starts(text, "网络四") ||
        starts(text, "网络五"))
      return sayNetwork(text);
    const char* key = classify(text);
    const auto* asset = find(key);
    if (!asset) return -ENOENT;
    std::printf("VOICE_PROMPT_ASSET key=%s frames=%u capture_frames=%u\n",
                key, unsigned(asset->frames), capture_frames);
    return k7sound_speak_mono16(asset->pcm, unsigned(asset->frames),
                                capture_frames);
  }

 private:
  struct SpokenToken { const char* text; const char* key; };

  static int play(const char* key) noexcept {
    const auto* asset = find(key);
    if (!asset) return -ENOENT;
    return k7sound_speak_mono16(asset->pcm, unsigned(asset->frames), 0);
  }

  static int sayNetwork(const std::string& text) noexcept {
    const char* number = starts(text, "网络一") ? "network_1" :
                         starts(text, "网络二") ? "network_2" :
                         starts(text, "网络三") ? "network_3" :
                         starts(text, "网络四") ? "network_4" : "network_5";
    int result = play(number);
    if (result) return result;
    const auto comma = text.find("，");
    if (comma == std::string::npos) return 0;
    std::string spoken = text.substr(comma + std::strlen("，"));
    if (spoken.size() >= std::strlen("。") &&
        spoken.compare(spoken.size() - std::strlen("。"), std::strlen("。"), "。") == 0)
      spoken.resize(spoken.size() - std::strlen("。"));
    return spellSsid(spoken);
  }

  static int spellSsid(const std::string& spoken) noexcept {
    // Ordered longest-first because spellings such as 艾夫 begin with 艾.
    static constexpr SpokenToken tokens[] = {
      {"下划线", "ssid_underscore"}, {"达不溜", "ssid_w"},
      {"艾克斯", "ssid_x"}, {"中文名称网络", "ssid_nonascii"},
      {"大写", "ssid_upper"}, {"艾夫", "ssid_f"}, {"艾尺", "ssid_h"},
      {"艾勒", "ssid_l"}, {"艾姆", "ssid_m"}, {"阿尔", "ssid_r"},
      {"艾丝", "ssid_s"}, {"贼德", "ssid_z"}, {"横杠", "ssid_dash"},
      {"空格", "ssid_space"}, {"符号", "ssid_symbol"},
      {"艾", "ssid_a"}, {"比", "ssid_b"}, {"西", "ssid_c"},
      {"迪", "ssid_d"}, {"伊", "ssid_e"}, {"吉", "ssid_g"},
      {"爱", "ssid_i"}, {"杰", "ssid_j"}, {"凯", "ssid_k"},
      {"恩", "ssid_n"}, {"欧", "ssid_o"}, {"皮", "ssid_p"},
      {"丘", "ssid_q"}, {"踢", "ssid_t"}, {"优", "ssid_u"},
      {"维", "ssid_v"}, {"歪", "ssid_y"}, {"零", "ssid_0"},
      {"一", "ssid_1"}, {"二", "ssid_2"}, {"三", "ssid_3"},
      {"四", "ssid_4"}, {"五", "ssid_5"}, {"六", "ssid_6"},
      {"七", "ssid_7"}, {"八", "ssid_8"}, {"九", "ssid_9"},
      {"点", "ssid_dot"},
    };
    std::size_t offset = 0;
    while (offset < spoken.size()) {
      bool matched = false;
      for (const auto& token : tokens) {
        const std::size_t length = std::strlen(token.text);
        if (spoken.compare(offset, length, token.text) != 0) continue;
        const int result = play(token.key);
        if (result) return result;
        offset += length;
        matched = true;
        break;
      }
      if (!matched) return play("ssid_nonascii");
    }
    return 0;
  }

  static bool starts(const std::string& text, const char* prefix) noexcept {
    const std::size_t length = std::strlen(prefix);
    return text.size() >= length && text.compare(0, length, prefix) == 0;
  }

  static bool has(const std::string& text, const char* part) noexcept {
    return text.find(part) != std::string::npos;
  }

  static const char* classify(const std::string& text) noexcept {
    if (has(text, "还没有联网")) return "wake";
    if (text == "请说话。" || text == "请说话") return "speak";
    if (has(text, "开始为你配置网络") || has(text, "网络配置已开始")) return "start";
    if (has(text, "正在扫描")) return "start";
    if (has(text, "发现以下网络")) return "found";
    if (has(text, "请说网络编号")) return "choose";
    if (has(text, "没有发现网络")) return "failed";
    if (has(text, "编号无效")) return "speak";
    if (starts(text, "已选择开放网络")) return "selected";
    if (starts(text, "已选择")) return "selected";
    if (has(text, "没有听清")) return "speak";
    if (starts(text, "已输入第") || starts(text, "当前长度为")) return "speak";
    if (starts(text, "密码共")) return "confirm";
    if (has(text, "尚未提交") || has(text, "确认请说")) return "confirm";
    if (has(text, "已清空") || has(text, "已重新开始")) return "selected";
    if (has(text, "切换到") || has(text, "切换输入")) return "speak";
    if (has(text, "密码长度不足") || has(text, "最大长度")) return "selected";
    if (has(text, "已收到凭据")) return "connecting";
    if (has(text, "正在连接网络")) return "connecting";
    if (starts(text, "已连接到") || has(text, "联网成功")) return "connected";
    if (has(text, "密码错误")) return "failed";
    if (has(text, "超时")) return "failed";
    if (has(text, "已取消")) return "failed";
    if (has(text, "连接失败") || has(text, "找不到") ||
        has(text, "暂不支持")) return "failed";
    return "failed";
  }

  static const k7_prompt_assets::Asset* find(const char* key) noexcept {
    for (const auto& asset : k7_prompt_assets::assets)
      if (std::strcmp(asset.key, key) == 0) return &asset;
    return nullptr;
  }
};
