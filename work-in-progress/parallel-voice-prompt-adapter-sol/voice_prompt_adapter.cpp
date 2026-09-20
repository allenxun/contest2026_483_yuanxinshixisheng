#include "voice_prompt_adapter.hpp"

#include <algorithm>
#include <array>
#include <cstring>

namespace voice_prompt {
namespace {

std::uint16_t le16(const std::uint8_t* p) {
  return static_cast<std::uint16_t>(p[0]) |
         static_cast<std::uint16_t>(p[1]) << 8;
}

std::uint32_t le32(const std::uint8_t* p) {
  return static_cast<std::uint32_t>(p[0]) |
         static_cast<std::uint32_t>(p[1]) << 8 |
         static_cast<std::uint32_t>(p[2]) << 16 |
         static_cast<std::uint32_t>(p[3]) << 24;
}

Result readExact(ResourcePort& resource, const CancelPort& cancel,
                 std::uint8_t* destination, std::size_t bytes) {
  std::size_t done = 0;
  while (done != bytes) {
    if (cancel.requested()) return Result::Cancelled;
    const std::ptrdiff_t n = resource.read(destination + done, bytes - done);
    if (n <= 0 || static_cast<std::size_t>(n) > bytes - done)
      return Result::ResourceIo;
    done += static_cast<std::size_t>(n);
  }
  return Result::Ok;
}

Result skipExact(ResourcePort& resource, const CancelPort& cancel,
                 std::uint32_t bytes) {
  std::array<std::uint8_t, 128> scratch{};
  while (bytes != 0) {
    const std::size_t amount = std::min<std::size_t>(bytes, scratch.size());
    const Result result = readExact(resource, cancel, scratch.data(), amount);
    if (result != Result::Ok) return result;
    bytes -= static_cast<std::uint32_t>(amount);
  }
  return Result::Ok;
}

Result findPcmData(ResourcePort& resource, const CancelPort& cancel,
                   std::uint32_t& data_bytes) {
  std::array<std::uint8_t, 12> riff{};
  Result result = readExact(resource, cancel, riff.data(), riff.size());
  if (result != Result::Ok) return result;
  if (std::memcmp(riff.data(), "RIFF", 4) != 0 ||
      std::memcmp(riff.data() + 8, "WAVE", 4) != 0)
    return Result::UnsupportedFormat;

  bool format_seen = false;
  for (unsigned chunks = 0; chunks != 32; ++chunks) {
    std::array<std::uint8_t, 8> header{};
    result = readExact(resource, cancel, header.data(), header.size());
    if (result != Result::Ok) return result;
    const std::uint32_t size = le32(header.data() + 4);
    if (std::memcmp(header.data(), "fmt ", 4) == 0) {
      if (size < 16) return Result::UnsupportedFormat;
      std::array<std::uint8_t, 16> format{};
      result = readExact(resource, cancel, format.data(), format.size());
      if (result != Result::Ok) return result;
      if (le16(format.data()) != 1 || le16(format.data() + 2) != 1 ||
          le32(format.data() + 4) != 16000 || le16(format.data() + 14) != 16)
        return Result::UnsupportedFormat;
      result = skipExact(resource, cancel, size - 16 + (size & 1u));
      if (result != Result::Ok) return result;
      format_seen = true;
    } else if (std::memcmp(header.data(), "data", 4) == 0) {
      if (!format_seen || size == 0 || (size & 1u))
        return Result::UnsupportedFormat;
      data_bytes = size;
      return Result::Ok;
    } else {
      result = skipExact(resource, cancel, size + (size & 1u));
      if (result != Result::Ok) return result;
    }
  }
  return Result::UnsupportedFormat;
}

Result failAfterAcquire(Result primary, AudioSinkPort& sink) {
  const bool cleaned = sink.abort();
  sink.release();
  return cleaned ? primary : Result::CleanupError;
}

}  // namespace

Result playFixedPrompt(const char* prompt_id, ResourcePort& resource,
                       AudioSinkPort& sink, const CancelPort& cancel,
                       PlaybackStats* stats) noexcept {
  if (stats) *stats = {};
  if (!prompt_id || prompt_id[0] == '\0') return Result::InvalidArgument;

  Result result = resource.open(prompt_id);
  if (result != Result::Ok) return result;

  std::uint32_t data_bytes = 0;
  result = findPcmData(resource, cancel, data_bytes);
  if (result != Result::Ok) {
    resource.close();
    return result;
  }

  result = sink.acquire();
  if (result != Result::Ok) {
    resource.close();
    return result;
  }
  if (!sink.begin(16000, 2)) {
    resource.close();
    return failAfterAcquire(Result::SinkError, sink);
  }

  // 256 frames = 16 ms, giving cancellation a fixed upper polling interval
  // when sink calls are themselves bounded by the backend contract.
  std::array<std::uint8_t, 512> pcm{};
  std::array<std::int32_t, 512> stereo{};
  std::uint32_t remaining = data_bytes;
  while (remaining != 0) {
    if (cancel.requested()) {
      resource.close();
      return failAfterAcquire(Result::Cancelled, sink);
    }
    const std::size_t bytes = std::min<std::size_t>(remaining, pcm.size());
    result = readExact(resource, cancel, pcm.data(), bytes);
    if (result != Result::Ok) {
      resource.close();
      return failAfterAcquire(result, sink);
    }
    const std::size_t frames = bytes / 2;
    for (std::size_t i = 0; i != frames; ++i) {
      const std::int16_t sample = static_cast<std::int16_t>(le16(&pcm[2 * i]));
      const std::int32_t expanded = static_cast<std::int32_t>(sample) * 65536;
      stereo[2 * i] = expanded;
      stereo[2 * i + 1] = expanded;
    }
    std::size_t submitted = 0;
    while (submitted != frames) {
      if (cancel.requested()) {
        resource.close();
        return failAfterAcquire(Result::Cancelled, sink);
      }
      const std::ptrdiff_t n = sink.writeFrames(
          stereo.data() + 2 * submitted, frames - submitted);
      if (stats) ++stats->write_calls;
      if (n <= 0 || static_cast<std::size_t>(n) > frames - submitted) {
        resource.close();
        return failAfterAcquire(Result::SinkError, sink);
      }
      submitted += static_cast<std::size_t>(n);
      if (stats) stats->frames_submitted += static_cast<std::uint32_t>(n);
    }
    remaining -= static_cast<std::uint32_t>(bytes);
    if (stats) stats->source_bytes += static_cast<std::uint32_t>(bytes);
  }

  resource.close();
  if (!sink.finish()) return failAfterAcquire(Result::SinkError, sink);
  sink.release();
  return Result::Ok;
}

const char* resultName(Result result) noexcept {
  switch (result) {
    case Result::Ok: return "ok";
    case Result::InvalidArgument: return "invalid_argument";
    case Result::ResourceMissing: return "resource_missing";
    case Result::ResourceIo: return "resource_io";
    case Result::UnsupportedFormat: return "unsupported_format";
    case Result::Busy: return "busy";
    case Result::Cancelled: return "cancelled";
    case Result::SinkError: return "sink_error";
    case Result::CleanupError: return "cleanup_error";
  }
  return "unknown";
}

}  // namespace voice_prompt
