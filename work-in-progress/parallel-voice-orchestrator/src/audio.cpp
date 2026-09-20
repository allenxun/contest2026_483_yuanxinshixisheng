#include "voicelink/audio.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <memory>

namespace voicelink {
std::int16_t floatToPcm16(float x) noexcept {
  if (std::isnan(x)) return 0;
  if (x >= 1.0f) return 32767;
  if (x <= -1.0f) return -32768;
  const long value = std::lround(x * 32768.0f);
  return static_cast<std::int16_t>(std::min(32767L, std::max(-32768L, value)));
}
float pcm16ToFloat(std::int16_t x) noexcept { return x / 32768.0f; }

SpeechSession::~SpeechSession() { close(); }
void SpeechSession::abortStream() noexcept {
  if (stream_) SherpaOnnxDestroyOnlineStream(stream_);
  stream_ = nullptr;
  finished_ = true;
}
void SpeechSession::close() noexcept {
  if (stream_) SherpaOnnxDestroyOnlineStream(stream_);
  if (recognizer_) SherpaOnnxDestroyOnlineRecognizer(recognizer_);
  if (tts_) SherpaOnnxDestroyOfflineTts(tts_);
  stream_ = nullptr;
  recognizer_ = nullptr;
  tts_ = nullptr;
  finished_ = false;
}
bool SpeechSession::initTts(const SherpaOnnxOfflineTtsConfig& t) {
  close();
  tts_ = SherpaOnnxCreateOfflineTts(&t);
  return tts_ != nullptr;
}
bool SpeechSession::initAsr(const SherpaOnnxOnlineRecognizerConfig& r) {
  close();
  recognizer_ = SherpaOnnxCreateOnlineRecognizer(&r);
  return recognizer_ != nullptr;
}
AudioStatus SpeechSession::speak(const char* text, PcmSink& sink,
                                const std::atomic_bool& stop) {
  if (!tts_ || !text) return AudioStatus::Invalid;
  if (stop.load()) return AudioStatus::Cancelled;
  using Audio = std::unique_ptr<const SherpaOnnxGeneratedAudio,
      decltype(&SherpaOnnxDestroyOfflineTtsGeneratedAudio)>;
  Audio audio(SherpaOnnxOfflineTtsGenerate(tts_, text, 0, 1.0f),
              SherpaOnnxDestroyOfflineTtsGeneratedAudio);
  if (!audio || !audio->samples || audio->n <= 0 || audio->sample_rate <= 0)
    return AudioStatus::Invalid;
  if (stop.load()) return AudioStatus::Cancelled;
  if (!sink.begin(audio->sample_rate)) return AudioStatus::IoError;
  struct End { PcmSink& sink; ~End() { sink.end(); } } end{sink};
  std::array<std::uint8_t, 1024> bytes{};
  for (std::int32_t offset = 0; offset < audio->n;) {
    if (stop.load()) return AudioStatus::Cancelled;
    const auto count = std::min<std::int32_t>(512, audio->n - offset);
    for (std::int32_t i = 0; i < count; ++i) {
      const auto v = static_cast<std::uint16_t>(floatToPcm16(audio->samples[offset + i]));
      bytes[2 * i] = static_cast<std::uint8_t>(v & 255);
      bytes[2 * i + 1] = static_cast<std::uint8_t>(v >> 8);
    }
    const auto size = static_cast<std::size_t>(count) * 2;
    std::size_t sent = 0;
    while (sent < size) {
      if (stop.load()) return AudioStatus::Cancelled;
      const auto n = sink.write(bytes.data() + sent, size - sent);
      if (n <= 0 || static_cast<std::size_t>(n) > size - sent) return AudioStatus::IoError;
      sent += static_cast<std::size_t>(n); // retain odd-byte short writes exactly
    }
    offset += count;
  }
  return AudioStatus::Ok;
}
bool SpeechSession::beginStream() {
  if (stream_) SherpaOnnxDestroyOnlineStream(stream_);
  stream_ = nullptr;
  finished_ = false;
  if (!recognizer_) return false;
  stream_ = SherpaOnnxCreateOnlineStream(recognizer_);
  return stream_ != nullptr;
}
AudioStatus SpeechSession::drain(const std::atomic_bool& stop, std::size_t budget) {
  while (SherpaOnnxIsOnlineStreamReady(recognizer_, stream_)) {
    if (stop.load()) return AudioStatus::Cancelled;
    if (budget-- == 0) return AudioStatus::DecodeLimit;
    SherpaOnnxDecodeOnlineStream(recognizer_, stream_);
  }
  return stop.load() ? AudioStatus::Cancelled : AudioStatus::Ok;
}
AudioStatus SpeechSession::feed(const std::int16_t* samples, std::size_t n,
                               int rate, const std::atomic_bool& stop,
                               std::size_t budget) {
  if (!stream_ || finished_) return AudioStatus::Invalid;
  if ((!samples && n) || rate <= 0 || n > 512) {
    abortStream();
    return AudioStatus::Invalid;
  }
  if (stop.load()) { abortStream(); return AudioStatus::Cancelled; }
  std::array<float, 512> normalized{};
  for (std::size_t i = 0; i < n; ++i) normalized[i] = pcm16ToFloat(samples[i]);
  if (n) SherpaOnnxOnlineStreamAcceptWaveform(stream_, rate, normalized.data(),
                                             static_cast<std::int32_t>(n));
  const auto status = drain(stop, budget);
  if (status != AudioStatus::Ok) abortStream();
  return status;
}
AudioStatus SpeechSession::finishWithTail(std::string& text,
                                         const std::atomic_bool& stop, int rate,
                                         unsigned tail_ms, std::size_t budget) {
  text.clear();
  if (!stream_ || finished_) return AudioStatus::Invalid;
  if (rate <= 0 || rate > 192000 || tail_ms > 2000) {
    abortStream();
    return AudioStatus::Invalid;
  }
  std::array<std::int16_t, 512> silence{};
  std::size_t remaining = static_cast<std::size_t>(rate) * tail_ms / 1000;
  while (remaining) {
    const auto count = std::min(remaining, silence.size());
    const auto status = feed(silence.data(), count, rate, stop, budget);
    if (status != AudioStatus::Ok) return status;
    remaining -= count;
  }
  return finish(text, stop, budget);
}
AudioStatus SpeechSession::finish(std::string& text, const std::atomic_bool& stop,
                                 std::size_t budget) {
  text.clear();
  if (!stream_ || finished_) return AudioStatus::Invalid;
  finished_ = true;
  // Release the stream on every exit, including result-copy allocation failure.
  using Stream = std::unique_ptr<const SherpaOnnxOnlineStream,
      decltype(&SherpaOnnxDestroyOnlineStream)>;
  struct Reset { const SherpaOnnxOnlineStream*& ptr; ~Reset() { ptr = nullptr; } } reset{stream_};
  Stream stream(stream_, SherpaOnnxDestroyOnlineStream);
  if (stop.load()) return AudioStatus::Cancelled;
  SherpaOnnxOnlineStreamInputFinished(stream_);
  auto status = drain(stop, budget);
  if (status != AudioStatus::Ok) return status;
  using Result = std::unique_ptr<const SherpaOnnxOnlineRecognizerResult,
      decltype(&SherpaOnnxDestroyOnlineRecognizerResult)>;
  Result result(SherpaOnnxGetOnlineStreamResult(recognizer_, stream_),
                SherpaOnnxDestroyOnlineRecognizerResult);
  if (!result || !result->text) return AudioStatus::Invalid;
  text = result->text;
  return AudioStatus::Ok;
}
bool SpeechSession::endpoint() const noexcept {
  return stream_ && SherpaOnnxOnlineStreamIsEndpoint(recognizer_, stream_);
}
} // namespace voicelink
