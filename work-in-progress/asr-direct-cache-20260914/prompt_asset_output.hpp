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
    const char* key = classify(text);
    const auto* asset = find(key);
    if (!asset) return -ENOENT;
    std::printf("VOICE_PROMPT_ASSET key=%s frames=%u capture_frames=%u\n",
                key, unsigned(asset->frames), capture_frames);
    return k7sound_speak_mono16(asset->pcm, unsigned(asset->frames),
                                capture_frames);
  }

 private:
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
    if (starts(text, "网络一")) return "network_1";
    if (starts(text, "网络二")) return "network_2";
    if (starts(text, "网络三")) return "network_3";
    if (starts(text, "网络四")) return "network_4";
    if (starts(text, "网络五")) return "network_5";
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
