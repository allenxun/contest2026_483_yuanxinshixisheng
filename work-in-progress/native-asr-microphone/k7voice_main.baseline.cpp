/* Native integration diagnostic. No fake speech input or success backend. */
#include "voice_wifi_adapter.hpp"
#include <cstdio>
#include <cstring>
#include <ctime>
#include <unistd.h>

#ifdef K7VOICE_NATIVE_ORT_ADD
extern "C" int k7_ort_add_probe(void);
#endif
#ifdef K7VOICE_NATIVE_ASR_MODEL
extern "C" int k7_asr_model_session_probe(void);
#endif

static bool now_ms(std::uint64_t &out)
{
  timespec t{};
  if (clock_gettime(CLOCK_MONOTONIC, &t) || t.tv_sec < 0) return false;
  out = std::uint64_t(t.tv_sec) * 1000 + std::uint64_t(t.tv_nsec) / 1000000;
  return true;
}

extern "C" int main(int argc, char **argv)
{
#ifdef K7VOICE_NATIVE_ASR_MODEL
  if (argc == 2 && !std::strcmp(argv[1], "asr-model"))
    return k7_asr_model_session_probe();
#endif
#ifdef K7VOICE_NATIVE_ORT_ADD
  if (argc == 2 && !std::strcmp(argv[1], "ort-add"))
    return k7_ort_add_probe();
#endif
  if (argc != 2 || (std::strcmp(argv[1], "probe") && std::strcmp(argv[1], "scan")))
    { std::puts("k7voice probe|scan (integration diagnostics; ASR/TTS unavailable)"); return 1; }
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
