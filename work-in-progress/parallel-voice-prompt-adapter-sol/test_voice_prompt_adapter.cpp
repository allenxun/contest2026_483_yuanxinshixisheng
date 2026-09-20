#include "voice_prompt_adapter.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

using voice_prompt::Result;

namespace {

void put16(std::vector<std::uint8_t>& out, std::uint16_t v) {
  out.push_back(static_cast<std::uint8_t>(v));
  out.push_back(static_cast<std::uint8_t>(v >> 8));
}
void put32(std::vector<std::uint8_t>& out, std::uint32_t v) {
  put16(out, static_cast<std::uint16_t>(v));
  put16(out, static_cast<std::uint16_t>(v >> 16));
}
void tag(std::vector<std::uint8_t>& out, const char* value) {
  out.insert(out.end(), value, value + 4);
}

std::vector<std::uint8_t> wav(unsigned frames) {
  std::vector<std::uint8_t> out;
  tag(out, "RIFF"); put32(out, 36 + frames * 2); tag(out, "WAVE");
  tag(out, "fmt "); put32(out, 16); put16(out, 1); put16(out, 1);
  put32(out, 16000); put32(out, 32000); put16(out, 2); put16(out, 16);
  tag(out, "data"); put32(out, frames * 2);
  for (unsigned i = 0; i != frames; ++i) put16(out, static_cast<std::uint16_t>(i - 3));
  return out;
}

struct Resource : voice_prompt::ResourcePort {
  std::vector<std::uint8_t> bytes{wav(600)};
  std::size_t at{};
  std::size_t max_read{bytes.size()};
  bool missing{};
  bool closed{};
  Result open(const char*) noexcept override {
    at = 0; closed = false; return missing ? Result::ResourceMissing : Result::Ok;
  }
  std::ptrdiff_t read(std::uint8_t* out, std::size_t capacity) noexcept override {
    const std::size_t n = std::min({capacity, max_read, bytes.size() - at});
    if (!n) return 0;
    std::memcpy(out, bytes.data() + at, n); at += n;
    return static_cast<std::ptrdiff_t>(n);
  }
  void close() noexcept override { closed = true; }
};

struct Cancel : voice_prompt::CancelPort {
  const unsigned* writes{};
  unsigned threshold{~0u};
  bool requested() const noexcept override {
    return writes && *writes >= threshold;
  }
};

struct Sink : voice_prompt::AudioSinkPort {
  Result acquire_result{Result::Ok};
  std::size_t max_write{~std::size_t{0}};
  unsigned writes{};
  int fail_write{-1};
  bool begin_ok{true}, finish_ok{true}, abort_ok{true};
  bool acquired{}, begun{}, finished{}, aborted{}, released{};
  Result acquire() noexcept override {
    if (acquire_result == Result::Ok) acquired = true;
    return acquire_result;
  }
  bool begin(std::uint32_t rate, std::uint8_t channels) noexcept override {
    begun = true; return begin_ok && rate == 16000 && channels == 2;
  }
  std::ptrdiff_t writeFrames(const std::int32_t* data,
                             std::size_t frames) noexcept override {
    if (fail_write >= 0 && writes == static_cast<unsigned>(fail_write)) {
      ++writes; return -1;
    }
    if (!data || !frames) return -1;
    ++writes;
    return static_cast<std::ptrdiff_t>(std::min(frames, max_write));
  }
  bool finish() noexcept override { finished = true; return finish_ok; }
  bool abort() noexcept override { aborted = true; return abort_ok; }
  void release() noexcept override { released = true; acquired = false; }
};

int failures;
#define CHECK(x) do { if (!(x)) { std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); ++failures; } } while (0)

void testShortReadAndWrite() {
  Resource r; r.max_read = 3;
  Sink s; s.max_write = 7;
  Cancel c; voice_prompt::PlaybackStats stats{};
  CHECK(voice_prompt::playFixedPrompt("p018", r, s, c, &stats) == Result::Ok);
  CHECK(stats.source_bytes == 1200 && stats.frames_submitted == 600);
  CHECK(stats.write_calls > 2 && r.closed && s.finished && s.released && !s.aborted);
}

void testCancelCleansUp() {
  Resource r; Sink s; s.max_write = 8;
  Cancel c; c.writes = &s.writes; c.threshold = 2;
  CHECK(voice_prompt::playFixedPrompt("p011", r, s, c, nullptr) == Result::Cancelled);
  CHECK(r.closed && s.aborted && s.released && !s.finished);
}

void testBusyDoesNotStart() {
  Resource r; Sink s; s.acquire_result = Result::Busy; Cancel c;
  CHECK(voice_prompt::playFixedPrompt("p011", r, s, c, nullptr) == Result::Busy);
  CHECK(r.closed && !s.begun && !s.aborted && !s.released);
}

void testWriteErrorCleansUp() {
  Resource r; Sink s; s.fail_write = 0; Cancel c;
  CHECK(voice_prompt::playFixedPrompt("p011", r, s, c, nullptr) == Result::SinkError);
  CHECK(r.closed && s.aborted && s.released && !s.finished);
}

void testCleanupFailureIsVisible() {
  Resource r; Sink s; s.fail_write = 0; s.abort_ok = false; Cancel c;
  CHECK(voice_prompt::playFixedPrompt("p011", r, s, c, nullptr) == Result::CleanupError);
  CHECK(s.aborted && s.released);
}

void testMissingResource() {
  Resource r; r.missing = true; Sink s; Cancel c;
  CHECK(voice_prompt::playFixedPrompt("absent", r, s, c, nullptr) == Result::ResourceMissing);
  CHECK(!r.closed && !s.acquired && !s.begun);
}

}  // namespace

int main() {
  testShortReadAndWrite();
  testCancelCleansUp();
  testBusyDoesNotStart();
  testWriteErrorCleansUp();
  testCleanupFailureIsVisible();
  testMissingResource();
  if (failures) return 1;
  std::puts("PASS 6/6: short I/O, cancel, busy, write cleanup, cleanup failure, missing resource");
  return 0;
}
