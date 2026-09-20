#include "voicelink/audio.hpp"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <vector>
using namespace voicelink;
namespace {
int failures{}, cases{};
#define CHECK(x) do { if (!(x)) { ++failures; std::cerr << __LINE__ << ": " #x "\n"; } } while (0)
int tts_live{}, recognizer_live{}, stream_live{}, audio_live{}, result_live{};
int ready{}, decodes{}, finishes{};
bool fail_tts{}, fail_recognizer{}, fail_stream{}, fail_result{}, stuck{};
int audio_mode{}; // 1=null, 2=missing samples, 3=zero, 4=negative, 5=bad rate
std::vector<float> accepted;
float generated[] = {-1, -0.5f, 0, 0.5f, 1};
}
// Fake implementations compile against the unmodified official C header.
// They exercise API use/ownership; no real model inference or ORT linking.
struct SherpaOnnxOfflineTts {};
struct SherpaOnnxOnlineRecognizer {};
struct SherpaOnnxOnlineStream {};
extern "C" {
const SherpaOnnxOfflineTts* SherpaOnnxCreateOfflineTts(const SherpaOnnxOfflineTtsConfig*) {
  if (fail_tts) return nullptr;
  ++tts_live; return new SherpaOnnxOfflineTts;
}
void SherpaOnnxDestroyOfflineTts(const SherpaOnnxOfflineTts* p) { if (p) { --tts_live; delete p; } }
const SherpaOnnxOnlineRecognizer* SherpaOnnxCreateOnlineRecognizer(const SherpaOnnxOnlineRecognizerConfig*) {
  if (fail_recognizer) return nullptr;
  ++recognizer_live; return new SherpaOnnxOnlineRecognizer;
}
void SherpaOnnxDestroyOnlineRecognizer(const SherpaOnnxOnlineRecognizer* p) { if (p) { CHECK(stream_live == 0); --recognizer_live; delete p; } }
const SherpaOnnxOnlineStream* SherpaOnnxCreateOnlineStream(const SherpaOnnxOnlineRecognizer*) {
  if (fail_stream) return nullptr;
  ++stream_live; ready = 0; return new SherpaOnnxOnlineStream;
}
void SherpaOnnxDestroyOnlineStream(const SherpaOnnxOnlineStream* p) { if (p) { --stream_live; delete p; } }
const SherpaOnnxGeneratedAudio* SherpaOnnxOfflineTtsGenerate(const SherpaOnnxOfflineTts*, const char*, int32_t, float) {
  if (audio_mode == 1) return nullptr;
  ++audio_live;
  return new SherpaOnnxGeneratedAudio{audio_mode == 2 ? nullptr : generated,
      audio_mode == 3 ? 0 : (audio_mode == 4 ? -1 : 5), audio_mode == 5 ? 0 : 22050};
}
void SherpaOnnxDestroyOfflineTtsGeneratedAudio(const SherpaOnnxGeneratedAudio* p) { if (p) { --audio_live; delete p; } }
void SherpaOnnxOnlineStreamAcceptWaveform(const SherpaOnnxOnlineStream*, int32_t rate, const float* p, int32_t n) {
  CHECK(rate == 16000); accepted.assign(p, p + n); ready += 3;
}
int32_t SherpaOnnxIsOnlineStreamReady(const SherpaOnnxOnlineRecognizer*, const SherpaOnnxOnlineStream*) { return stuck || ready > 0; }
void SherpaOnnxDecodeOnlineStream(const SherpaOnnxOnlineRecognizer*, const SherpaOnnxOnlineStream*) { CHECK(ready > 0 || stuck); ++decodes; if (ready) --ready; }
void SherpaOnnxOnlineStreamInputFinished(const SherpaOnnxOnlineStream*) { ++finishes; ready += 2; }
int32_t SherpaOnnxOnlineStreamIsEndpoint(const SherpaOnnxOnlineRecognizer*, const SherpaOnnxOnlineStream*) { CHECK(ready == 0); return 1; }
const SherpaOnnxOnlineRecognizerResult* SherpaOnnxGetOnlineStreamResult(const SherpaOnnxOnlineRecognizer*, const SherpaOnnxOnlineStream*) {
  CHECK(ready == 0);
  if (fail_result) return nullptr;
  ++result_live; auto r = new SherpaOnnxOnlineRecognizerResult{}; r->text = "synthetic recognition"; return r;
}
void SherpaOnnxDestroyOnlineRecognizerResult(const SherpaOnnxOnlineRecognizerResult* p) { if (p) { --result_live; delete p; } }
}
namespace {
struct Sink : PcmSink {
  std::vector<std::uint8_t> bytes;
  int rate{}, ends{}, writes{};
  std::ptrdiff_t limit{3};
  bool fail_begin{}, oversize{};
  std::atomic_bool* stop{};
  bool begin(int r) noexcept override { rate = r; return !fail_begin; }
  std::ptrdiff_t write(const std::uint8_t* p, std::size_t n) noexcept override {
    ++writes;
    if (oversize) return static_cast<std::ptrdiff_t>(n) + 1;
    if (limit <= 0) return limit;
    auto count = std::min(n, static_cast<std::size_t>(limit)); bytes.insert(bytes.end(), p, p + count);
    if (stop) stop->store(true);
    return static_cast<std::ptrdiff_t>(count);
  }
  void end() noexcept override { ++ends; }
};
void conversion() {
  ++cases;
  CHECK(floatToPcm16(-1) == -32768); CHECK(floatToPcm16(1) == 32767);
  CHECK(floatToPcm16(-0.5f) == -16384); CHECK(floatToPcm16(0.5f) == 16384);
  CHECK(floatToPcm16(0) == 0); CHECK(floatToPcm16(99) == 32767);
  CHECK(floatToPcm16(-99) == -32768); CHECK(floatToPcm16(std::numeric_limits<float>::quiet_NaN()) == 0);
  CHECK(floatToPcm16(std::numeric_limits<float>::infinity()) == 32767);
  CHECK(floatToPcm16(-std::numeric_limits<float>::infinity()) == -32768);
  CHECK(floatToPcm16(0.5f / 32768) == 1); CHECK(floatToPcm16(-0.5f / 32768) == -1);
  for (int i = -32768; i <= 32767; ++i) CHECK(floatToPcm16(pcm16ToFloat(static_cast<std::int16_t>(i))) == i);
}
void playback() {
  SpeechSession s; CHECK(s.init({}, {})); std::atomic_bool stop{false};
  ++cases; Sink good; CHECK(s.speak("test", good, stop) == AudioStatus::Ok);
  CHECK(good.rate == 22050); CHECK(good.ends == 1); CHECK(good.writes == 4);
  CHECK(good.bytes == std::vector<std::uint8_t>({0,128,0,192,0,0,0,64,255,127})); CHECK(audio_live == 0);
  for (int mode = 1; mode <= 5; ++mode) {
    ++cases; audio_mode = mode; Sink sink; CHECK(s.speak("test", sink, stop) == AudioStatus::Invalid);
    CHECK(audio_live == 0); CHECK(sink.ends == 0);
  }
  audio_mode = 0;
  for (int limit : {0, -1}) {
    ++cases; Sink sink; sink.limit = limit; CHECK(s.speak("test", sink, stop) == AudioStatus::IoError);
    CHECK(sink.ends == 1); CHECK(sink.writes == 1); CHECK(audio_live == 0);
  }
  ++cases; Sink large; large.oversize = true; CHECK(s.speak("test", large, stop) == AudioStatus::IoError); CHECK(large.ends == 1);
  ++cases; Sink fail; fail.fail_begin = true; CHECK(s.speak("test", fail, stop) == AudioStatus::IoError);
  CHECK(fail.ends == 0); CHECK(audio_live == 0);
  ++cases; Sink cancel; cancel.stop = &stop; CHECK(s.speak("test", cancel, stop) == AudioStatus::Cancelled);
  CHECK(cancel.ends == 1); CHECK(audio_live == 0);
  ++cases; Sink pre; CHECK(s.speak("test", pre, stop) == AudioStatus::Cancelled); CHECK(pre.rate == 0);
}
void streaming() {
  SpeechSession s; CHECK(s.init({}, {})); CHECK(s.beginStream()); std::atomic_bool stop{false};
  std::int16_t samples[] = {-32768, 0, 32767};
  ++cases; decodes = 0; CHECK(s.feed(samples, 3, 16000, stop) == AudioStatus::Ok);
  CHECK(decodes == 3); CHECK(accepted[0] == -1); CHECK(accepted[1] == 0); CHECK(accepted[2] < 1);
  CHECK(s.endpoint()); std::string text; CHECK(s.finish(text, stop) == AudioStatus::Ok);
  CHECK(decodes == 5); CHECK(text == "synthetic recognition"); CHECK(result_live == 0); CHECK(stream_live == 0);
  CHECK(s.feed(samples, 3, 16000, stop) == AudioStatus::Invalid);
  CHECK(s.finish(text, stop) == AudioStatus::Invalid);
  ++cases; CHECK(s.beginStream()); fail_result = true; CHECK(s.finish(text, stop) == AudioStatus::Invalid);
  CHECK(stream_live == 0); fail_result = false;
  ++cases; CHECK(s.beginStream()); CHECK(s.feed(nullptr, 1, 16000, stop) == AudioStatus::Invalid);
  CHECK(stream_live == 0); CHECK(s.beginStream());
  CHECK(s.feed(samples, 513, 16000, stop) == AudioStatus::Invalid);
  CHECK(stream_live == 0); CHECK(s.beginStream());
  CHECK(s.feed(samples, 3, 0, stop) == AudioStatus::Invalid);
  CHECK(stream_live == 0); CHECK(s.beginStream());
  CHECK(s.feed(nullptr, 0, 16000, stop) == AudioStatus::Ok);
  ++cases; stuck = true; decodes = 0; CHECK(s.feed(samples, 3, 16000, stop, 4) == AudioStatus::DecodeLimit);
  CHECK(decodes == 4); CHECK(stream_live == 0);
  CHECK(s.finish(text, stop, 2) == AudioStatus::Invalid);
  CHECK(s.beginStream()); CHECK(s.finish(text, stop, 2) == AudioStatus::DecodeLimit); CHECK(stream_live == 0); stuck = false;
  ++cases; CHECK(s.beginStream()); stop = true; CHECK(s.feed(samples, 3, 16000, stop) == AudioStatus::Cancelled);
  CHECK(stream_live == 0); CHECK(s.finish(text, stop) == AudioStatus::Invalid);
  CHECK(s.beginStream()); CHECK(s.finish(text, stop) == AudioStatus::Cancelled); CHECK(stream_live == 0);
  ++cases; stop = false; CHECK(s.beginStream()); CHECK(s.beginStream()); CHECK(stream_live == 1);
  s.close(); s.close(); CHECK(stream_live == 0); CHECK(tts_live == 0); CHECK(recognizer_live == 0);
}
void initialization() {
  ++cases; SpeechSession s; fail_tts = true; CHECK(!s.init({}, {})); CHECK(tts_live == 0); fail_tts = false;
  ++cases; fail_recognizer = true; CHECK(!s.init({}, {})); CHECK(tts_live == 0); fail_recognizer = false;
  ++cases; CHECK(s.init({}, {})); fail_stream = true; CHECK(!s.beginStream()); CHECK(stream_live == 0); fail_stream = false;
  ++cases; CHECK(s.init({}, {})); CHECK(tts_live == 1); CHECK(recognizer_live == 1); CHECK(s.beginStream());
  // Destructor must release stream before recognizer, then TTS.
}
}
int main() {
  conversion(); playback(); streaming(); initialization();
  CHECK(tts_live == 0 && recognizer_live == 0 && stream_live == 0 && audio_live == 0 && result_live == 0);
  std::cout << "audio cases=" << cases << " failures=" << failures << "\n";
  return failures ? EXIT_FAILURE : EXIT_SUCCESS;
}
