#pragma once
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <string>
#include <sherpa-onnx/c-api/c-api.h>

namespace voicelink {
std::int16_t floatToPcm16(float sample) noexcept;
float pcm16ToFloat(std::int16_t sample) noexcept;
enum class AudioStatus { Ok, Invalid, IoError, Cancelled, DecodeLimit };

class PcmSink {
 public:
  virtual ~PcmSink() = default;
  // Mono signed PCM16 little endian. A failed begin must release partial setup.
  virtual bool begin(int sample_rate) noexcept = 0;
  // Returns bytes consumed; 0/negative is terminal (no busy retry).
  // Driver implements EINTR/EAGAIN readiness/deadline handling internally.
  virtual std::ptrdiff_t write(const std::uint8_t*, std::size_t) noexcept = 0;
  virtual void end() noexcept = 0;
};

// Owns recognizer/TTS. Single owner thread; only stop flag may be set cross-thread.
// Config strings must remain valid through init. No board/audio device access.
class SpeechSession {
 public:
  SpeechSession() = default;
  ~SpeechSession();
  SpeechSession(const SpeechSession&) = delete;
  SpeechSession& operator=(const SpeechSession&) = delete;
  // Exclusive model ownership: destruction completes before the next create.
  bool initAsr(const SherpaOnnxOnlineRecognizerConfig&);
  bool initTts(const SherpaOnnxOfflineTtsConfig&);
  void close() noexcept;
  AudioStatus speak(const char*, PcmSink&, const std::atomic_bool& stop);
  bool beginStream();
  AudioStatus feed(const std::int16_t*, std::size_t, int sample_rate,
                   const std::atomic_bool& stop, std::size_t decode_budget = 1024);
  AudioStatus finish(std::string&, const std::atomic_bool& stop,
                     std::size_t decode_budget = 1024);
  // Explicit model profile, not a universal ASR default. Real Paraformer v1.12.14
  // tested with 300 ms at 16 kHz. Bounded to 2 s / 192 kHz; no feed after EOF.
  AudioStatus finishWithTail(std::string&, const std::atomic_bool& stop,
                            int sample_rate, unsigned tail_ms,
                            std::size_t decode_budget = 1024);
  bool endpoint() const noexcept;
 private:
  void abortStream() noexcept;
  AudioStatus drain(const std::atomic_bool&, std::size_t);
  const SherpaOnnxOfflineTts* tts_{};
  const SherpaOnnxOnlineRecognizer* recognizer_{};
  const SherpaOnnxOnlineStream* stream_{};
  bool finished_{};
};
} // namespace voicelink
