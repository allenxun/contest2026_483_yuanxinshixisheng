/* Native integration diagnostic. No fake speech input or success backend. */
#include "voicelink/asr_runtime.h"
#include "voicelink/controller.hpp"
#include "voicelink/voice_loop.hpp"
#include "voice_wifi_adapter.hpp"
#include "k7sound_api.h"
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <unistd.h>

#ifdef K7VOICE_NATIVE_ORT_ADD
extern "C" int k7_ort_add_probe(void);
#endif
static bool now_ms(std::uint64_t &out)
{
  timespec t{};
  if (clock_gettime(CLOCK_MONOTONIC, &t) || t.tv_sec < 0) return false;
  out = std::uint64_t(t.tv_sec) * 1000 + std::uint64_t(t.tv_nsec) / 1000000;
  return true;
}

namespace {

class ConsoleTts final : public voicelink::TtsPort
{
 public:
  bool speak(const std::string &text) override
  {
    std::printf("VOICE_PROMPT %s\n", text.c_str());
    return true;
  }

  void stop() override {}
};

class MonotonicClock final : public voicelink::ClockPort
{
 public:
  std::uint64_t nowMs() const noexcept override
  {
    std::uint64_t value = 0;
    return now_ms(value) ? value : 0;
  }
};

int run_controller_scan()
{
  auto port = voicelink::nativeWifiPort();
  if (!port)
    {
      std::puts("VOICE_FLOW native_network=0");
      return 1;
    }
  ConsoleTts tts;
  MonotonicClock clock;
  voicelink::Controller controller(tts, *port, clock);
  controller.start();
  controller.ingest("开始联网");
  while (controller.context().state == voicelink::State::ScanningWifi)
    {
      controller.poll();
      usleep(10000);
    }
  const auto &context = controller.context();
  std::printf("VOICE_FLOW state=%u grammar=%u count=%u\n",
              unsigned(context.state), unsigned(context.grammar),
              unsigned(context.candidates.size()));
  return context.state == voicelink::State::WaitingNetworkChoice ? 0 : 1;
}

#ifdef K7VOICE_NATIVE_ASR_MIC
class PromptToneTts final : public voicelink::TtsPort
{
 public:
  bool speak(const std::string &text) override
  {
    std::printf("VOICE_PROMPT %s\n", text.c_str());
    return k7sound_play_prompt_tone() == 0;
  }

  void stop() override {}
};

class SynchronousCapturePort final : public voice_loop::CapturePort
{
 public:
  voice_loop::CaptureResult begin(voicelink::Grammar) noexcept override
  {
    const auto id = ++next_id_;
    const int error = k7sound_capture_grouped(48000);
    return {error ? voice_loop::CaptureStatus::Failed
                  : voice_loop::CaptureStatus::Complete,
            id, error};
  }

  voice_loop::CaptureResult poll(std::uint64_t id) noexcept override
  {
    return {voice_loop::CaptureStatus::Failed, id, -EIO};
  }

  void cancel(std::uint64_t) noexcept override {}
  void release(std::uint64_t) noexcept override {}

 private:
  std::uint64_t next_id_{};
};

class SynchronousAsrPort final : public voice_loop::AsrPort
{
 public:
  voice_loop::AsrResult begin(std::uint64_t, voicelink::Grammar) noexcept override
  {
    const auto id = ++next_id_;
    char text[256]{};
    const int error = k7_asr_microphone_text(text, sizeof(text));
    if (error) return {voice_loop::AsrStatus::Failed, id, error, {}};
    return {voice_loop::AsrStatus::Ready, id, 0, text};
  }

  voice_loop::AsrResult poll(std::uint64_t id) noexcept override
  {
    return {voice_loop::AsrStatus::Failed, id, -EIO, {}};
  }

  void cancel(std::uint64_t) noexcept override {}

 private:
  std::uint64_t next_id_{};
};

int run_controller_microphone_wake()
{
  auto port = voicelink::nativeWifiPort();
  if (!port)
    {
      std::puts("VOICE_FLOW native_network=0");
      return 1;
    }
  char text[256]{};
  const int asr = k7_asr_microphone_text(text, sizeof(text));
  if (asr)
    {
      std::printf("VOICE_FLOW asr_error=%d\n", asr);
      return 1;
    }
  std::printf("VOICE_FLOW wake_text=%s bytes=%u\n", text,
              unsigned(std::strlen(text)));
  ConsoleTts tts;
  MonotonicClock clock;
  voicelink::Controller controller(tts, *port, clock);
  controller.start();
  controller.ingest(text);
  while (controller.context().state == voicelink::State::ScanningWifi)
    {
      controller.poll();
      usleep(10000);
    }
  const auto &context = controller.context();
  std::printf("VOICE_FLOW mic_state=%u grammar=%u count=%u\n",
              unsigned(context.state), unsigned(context.grammar),
              unsigned(context.candidates.size()));
  return context.state == voicelink::State::WaitingNetworkChoice ? 0 : 1;
}

int run_controller_microphone_provision()
{
  auto port = voicelink::nativeWifiPort();
  if (!port)
    {
      std::puts("VOICE_FLOW native_network=0");
      return 1;
    }
  PromptToneTts tts;
  MonotonicClock clock;
  voicelink::Controller controller(tts, *port, clock);
  SynchronousCapturePort capture;
  SynchronousAsrPort asr;
  voice_loop::Config config;
  config.capture_timeout_ms = 10000;
  config.asr_timeout_ms = 180000;
  config.max_text_bytes = 255;
  voice_loop::Loop loop(controller, capture, asr, clock, config);
  std::puts("VOICE_PROVISION ready; speak after each prompt tone");
  if (k7sound_play_prompt_tone() || !loop.start()) return 1;
  const auto started = clock.nowMs();
  while (loop.phase() != voice_loop::Phase::Completed &&
         loop.phase() != voice_loop::Phase::Error &&
         loop.phase() != voice_loop::Phase::Idle)
    {
      const auto now = clock.nowMs();
      if (now < started || now - started >= 600000)
        {
          loop.cancel();
          std::puts("VOICE_PROVISION timeout");
          return 1;
        }
      loop.tick();
      usleep(10000);
    }
  std::printf("VOICE_PROVISION phase=%u turns=%llu error=%d\n",
              unsigned(loop.phase()),
              static_cast<unsigned long long>(loop.turn()), loop.lastError());
  return loop.phase() == voice_loop::Phase::Completed ? 0 : 1;
}
#endif

}  // namespace

extern "C" int main(int argc, char **argv)
{
#ifdef K7VOICE_NATIVE_ASR_MODEL
  if (argc == 2 && !std::strcmp(argv[1], "asr-model"))
    return k7_asr_model_session_probe();
#ifdef K7VOICE_NATIVE_ASR_MIC
  if (argc == 2 && !std::strcmp(argv[1], "asr-mic"))
    return k7_asr_microphone_probe();
#endif
#endif
#ifdef K7VOICE_NATIVE_ORT_ADD
  if (argc == 2 && !std::strcmp(argv[1], "ort-add"))
    return k7_ort_add_probe();
#endif
#ifdef K7VOICE_NATIVE_ASR_MIC
  if (argc == 2 && !std::strcmp(argv[1], "flow-mic-wake"))
    return run_controller_microphone_wake();
  if (argc == 2 && !std::strcmp(argv[1], "flow-mic-provision"))
    return run_controller_microphone_provision();
#endif
  if (argc == 2 && !std::strcmp(argv[1], "flow-scan"))
    return run_controller_scan();
  if (argc != 2 || (std::strcmp(argv[1], "probe") && std::strcmp(argv[1], "scan")))
    {
      std::puts("k7voice probe|scan|flow-scan|flow-mic-wake|flow-mic-provision|asr-model|asr-mic");
      std::puts("flow-scan uses the formal Controller with real Wi-Fi and console prompts");
      std::puts("flow-mic-wake consumes the last completed microphone capture");
      return 1;
    }
  auto port = voicelink::nativeWifiPort();
  std::printf("VOICE native_network=%d asr=0 tts=0 speech_provisioning=0\n", !!port);
  if (!port) return 1;
  if (!std::strcmp(argv[1], "probe")) return 0;
  std::uint64_t id = 0, start = 0, now = 0;
  if (!now_ms(start)) return 1;
  try
    {
      auto r = port->beginScan(); id = r.request_id;
      std::printf("VOICE scan accepted=%d id=%llu error=%d\n",
        r.status == voicelink::ScanStatus::Received,
        static_cast<unsigned long long>(id), r.error_code);
      if (r.status != voicelink::ScanStatus::Received) return 1;
      for (;;)
        {
          if (!now_ms(now) || now < start || now - start >= 35000)
            { port->cancelScan(id); std::puts("VOICE scan timeout; cancellation requested, service retains cleanup ownership"); return 1; }
          r = port->pollScan(id);
          if (r.status == voicelink::ScanStatus::Received || r.status == voicelink::ScanStatus::Scanning)
            { usleep(10000); continue; }
          if (r.status != voicelink::ScanStatus::Ready)
            { port->cancelScan(id); std::printf("VOICE scan terminal=%u error=%d\n", unsigned(r.status), r.error_code); return 1; }
          std::printf("VOICE scan_done id=%llu count=%u\n", static_cast<unsigned long long>(id), unsigned(r.access_points.size()));
          // Names are rendered as bytes to prevent SSID control text affecting logs.
          for (const auto &ap : r.access_points)
            {
              std::printf("VOICE AP ssid_hex=");
              for (unsigned char c : ap.ssid) std::printf("%02x", unsigned(c));
              std::printf("\n");
            }
          return 0;
        }
    }
  catch (...)
    { if (id) port->cancelScan(id); std::puts("VOICE scan exception; cleanup owned by service"); return 1; }
}
