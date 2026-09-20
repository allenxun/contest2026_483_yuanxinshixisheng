#include "tool_executor.hpp"

#include <algorithm>
#include <charconv>
#include <cstdio>
#include <cstring>
#include <limits>

namespace velavision::tools {
namespace {

class Cursor {
 public:
  explicit Cursor(std::string_view text) : text_(text) {}
  void ws() noexcept { while (pos_ < text_.size() && (text_[pos_] == ' ' || text_[pos_] == '\t' || text_[pos_] == '\r' || text_[pos_] == '\n')) ++pos_; }
  bool take(char c) noexcept { ws(); if (pos_ >= text_.size() || text_[pos_] != c) return false; ++pos_; return true; }
  bool literal(std::string_view value) noexcept { ws(); if (text_.substr(pos_, value.size()) != value) return false; pos_ += value.size(); return true; }
  bool quoted(std::string_view& out) noexcept {
    ws();
    if (pos_ >= text_.size() || text_[pos_++] != '"') return false;
    const std::size_t begin = pos_;
    while (pos_ < text_.size() && text_[pos_] != '"') {
      const unsigned char c = static_cast<unsigned char>(text_[pos_]);
      if (c < 0x20 || c > 0x7e || c == '\\') return false;
      ++pos_;
    }
    if (pos_ >= text_.size()) return false;
    out = text_.substr(begin, pos_ - begin);
    ++pos_;
    return true;
  }
  bool u32(std::uint32_t& out) noexcept {
    ws();
    const std::size_t begin = pos_;
    while (pos_ < text_.size() && text_[pos_] >= '0' && text_[pos_] <= '9') ++pos_;
    if (begin == pos_ || (pos_ - begin > 1 && text_[begin] == '0')) return false;
    const auto* first = text_.data() + begin;
    const auto* last = text_.data() + pos_;
    return std::from_chars(first, last, out).ec == std::errc{};
  }
  bool end() noexcept { ws(); return pos_ == text_.size(); }

 private:
  std::string_view text_;
  std::size_t pos_{};
};

bool hasSensitiveField(std::string_view value) noexcept {
  return value.find("\"password\"") != std::string_view::npos ||
         value.find("\"passphrase\"") != std::string_view::npos ||
         value.find("\"psk\"") != std::string_view::npos;
}

const char* stateName(State state) noexcept {
  switch (state) {
    case State::Accepted: return "accepted";
    case State::Running: return "running";
    case State::Succeeded: return "succeeded";
    case State::Failed: return "failed";
    case State::Cancelled: return "cancelled";
    case State::TimedOut: return "timed_out";
    default: return "unknown";
  }
}

template <std::size_t N>
std::string_view boundedView(const char (&value)[N]) noexcept {
  const void* end = std::memchr(value, '\0', N);
  return {value, end ? static_cast<const char*>(end) - value : N};
}

template <std::size_t N>
std::string_view boundedView(const std::array<char, N>& value) noexcept {
  const void* end = std::memchr(value.data(), '\0', N);
  return {value.data(), end ? static_cast<const char*>(end) - value.data() : N};
}

bool resultWellFormed(const Call& call, const PortResult& result) noexcept {
  if (result.state != PortState::Succeeded || result.error != PortError::None) return true;
  if (call.tool == Tool::PhotoCapture) {
    const auto value = boundedView(result.asset_id);
    return !value.empty() && value.size() < sizeof(result.asset_id);
  }
  if (call.tool == Tool::DeviceStatus) return result.battery_percent <= 100;
  if (result.ssid_count > result.ssids.size()) return false;
  for (std::size_t i = 0; i < result.ssid_count; ++i) {
    const auto value = boundedView(result.ssids[i]);
    if (value.empty() || value.size() == result.ssids[i].size()) return false;
  }
  return true;
}

class Writer {
 public:
  explicit Writer(Response& response) : response_(response) {}
  void append(std::string_view value) noexcept {
    const std::size_t room = response_.bytes.size() - response_.size;
    const std::size_t count = std::min(room, value.size());
    if (count) std::memcpy(response_.bytes.data() + response_.size, value.data(), count);
    response_.size += count;
    response_.truncated = response_.truncated || count != value.size();
  }
  void number(std::uint64_t value) noexcept {
    char buf[32]{};
    const int n = std::snprintf(buf, sizeof(buf), "%llu", static_cast<unsigned long long>(value));
    if (n > 0) append({buf, static_cast<std::size_t>(n)});
  }
  void quoted(std::string_view value) noexcept {
    append("\"");
    for (char c : value) {
      if (c == '"' || c == '\\') { append("\\"); append({&c, 1}); }
      else if (static_cast<unsigned char>(c) >= 0x20) append({&c, 1});
    }
    append("\"");
  }
 private:
  Response& response_;
};

}  // namespace

ParseResult parseModelCall(std::string_view input) noexcept {
  ParseResult result{};
  if (input.size() > kMaxRequestBytes) { result.error = ParseError::TooLarge; return result; }
  if (hasSensitiveField(input)) { result.error = ParseError::SensitiveField; return result; }
  Cursor c(input);
  std::string_view key;
  std::string_view tool;
  std::uint32_t version{};
  std::uint32_t timeout{};
  if (!c.take('{') || !c.quoted(key) || key != "version" || !c.take(':') || !c.u32(version) || version != 1 ||
      !c.take(',') || !c.quoted(key) || key != "tool" || !c.take(':') || !c.quoted(tool) ||
      !c.take(',') || !c.quoted(key) || key != "args" || !c.take(':') || !c.take('{')) {
    result.error = ParseError::Schema;
    return result;
  }
  if (tool == "photo.capture") {
    std::uint32_t camera{};
    if (!c.quoted(key) || key != "camera" || !c.take(':') || !c.u32(camera) || camera > 2 || !c.take('}')) { result.error = ParseError::Schema; return result; }
    result.call.tool = Tool::PhotoCapture;
    result.call.camera = static_cast<std::uint8_t>(camera);
  } else if (tool == "device.status") {
    if (!c.take('}')) { result.error = ParseError::Schema; return result; }
    result.call.tool = Tool::DeviceStatus;
  } else if (tool == "network.scan") {
    std::uint32_t limit{};
    if (!c.quoted(key) || key != "limit" || !c.take(':') || !c.u32(limit) || limit < 1 || limit > 8 || !c.take('}')) { result.error = ParseError::Schema; return result; }
    result.call.tool = Tool::NetworkScan;
    result.call.scan_limit = static_cast<std::uint8_t>(limit);
  } else {
    result.error = ParseError::UnknownTool;
    return result;
  }
  if (!c.take(',') || !c.quoted(key) || key != "timeout_ms" || !c.take(':') || !c.u32(timeout) || timeout < 1 || timeout > 30000 || !c.take('}') || !c.end()) {
    result.error = ParseError::Schema;
    return result;
  }
  result.call.timeout_ms = timeout;
  result.error = ParseError::None;
  return result;
}

Executor::Entry* Executor::find(std::uint64_t request_id) noexcept {
  for (auto& entry : entries_) if (entry.state != State::Empty && entry.request_id == request_id) return &entry;
  return nullptr;
}
const Executor::Entry* Executor::find(std::uint64_t request_id) const noexcept {
  for (const auto& entry : entries_) if (entry.state != State::Empty && entry.request_id == request_id) return &entry;
  return nullptr;
}

SubmitResult Executor::submit(std::uint64_t request_id, std::string_view json, std::uint64_t now_ms) noexcept {
  if (!request_id) return {SubmitError::InvalidRequestId, ParseError::None, 0, State::Empty};
  if (find(request_id)) return {SubmitError::DuplicateRequestId, ParseError::None, 0, State::Empty};
  const ParseResult parsed = parseModelCall(json);
  if (!parsed) return {SubmitError::Parse, parsed.error, 0, State::Empty};
  Entry* slot = nullptr;
  for (auto& entry : entries_) if (entry.state == State::Empty) { slot = &entry; break; }
  if (!slot) return {SubmitError::Capacity, ParseError::None, 0, State::Empty};
  if (!next_transaction_id_) return {SubmitError::IdExhausted, ParseError::None, 0, State::Empty};
  slot->request_id = request_id;
  slot->transaction_id = next_transaction_id_++;
  slot->deadline_ms = parsed.call.timeout_ms > std::numeric_limits<std::uint64_t>::max() - now_ms
                          ? std::numeric_limits<std::uint64_t>::max()
                          : now_ms + parsed.call.timeout_ms;
  slot->state = State::Accepted;
  slot->call = parsed.call;
  if (!port_.start(slot->transaction_id, slot->call)) {
    slot->state = State::Failed;
    slot->result = {PortState::Failed, PortError::Rejected};
    return {SubmitError::PortRejected, ParseError::None, slot->transaction_id, slot->state};
  }
  return {SubmitError::None, ParseError::None, slot->transaction_id, slot->state};
}

State Executor::poll(std::uint64_t request_id, std::uint64_t now_ms) noexcept {
  Entry* entry = find(request_id);
  if (!entry) return State::Empty;
  if (entry->state == State::Succeeded || entry->state == State::Failed || entry->state == State::Cancelled || entry->state == State::TimedOut) return entry->state;
  if (now_ms >= entry->deadline_ms) {
    port_.cancel(entry->transaction_id);
    entry->state = State::TimedOut;
    return entry->state;
  }
  entry->result = port_.poll(entry->transaction_id);
  if (!resultWellFormed(entry->call, entry->result)) {
    entry->result = {PortState::Failed, PortError::Protocol};
    entry->state = State::Failed;
    return entry->state;
  }
  if (entry->result.state == PortState::Running) entry->state = State::Running;
  else if (entry->result.state == PortState::Succeeded) entry->state = State::Succeeded;
  else entry->state = State::Failed;
  return entry->state;
}

bool Executor::cancel(std::uint64_t request_id) noexcept {
  Entry* entry = find(request_id);
  if (!entry || entry->state == State::Succeeded || entry->state == State::Failed || entry->state == State::Cancelled || entry->state == State::TimedOut) return false;
  port_.cancel(entry->transaction_id);
  entry->state = State::Cancelled;
  return true;
}

Response Executor::response(std::uint64_t request_id) const noexcept {
  Response response{};
  Writer w(response);
  const Entry* entry = find(request_id);
  if (!entry) { w.append("{\"error\":\"unknown_request\"}"); return response; }
  w.append("{\"request_id\":"); w.number(entry->request_id);
  w.append(",\"transaction_id\":"); w.number(entry->transaction_id);
  w.append(",\"state\":"); w.quoted(stateName(entry->state));
  if (entry->state == State::Succeeded) {
    w.append(",\"result\":{");
    if (entry->call.tool == Tool::PhotoCapture) { w.append("\"asset_id\":"); w.quoted(boundedView(entry->result.asset_id)); }
    else if (entry->call.tool == Tool::DeviceStatus) {
      w.append("\"wifi_connected\":"); w.append(entry->result.wifi_connected ? "true" : "false");
      w.append(",\"battery_percent\":"); w.number(entry->result.battery_percent);
    } else {
      w.append("\"ssids\":[");
      const std::size_t count = std::min<std::size_t>({entry->result.ssid_count, entry->call.scan_limit, entry->result.ssids.size()});
      for (std::size_t i = 0; i < count; ++i) { if (i) w.append(","); w.quoted(boundedView(entry->result.ssids[i])); }
      w.append("]");
    }
    w.append("}");
  } else if (entry->state == State::Failed) {
    w.append(",\"error\":\"execution_failed\"");
  }
  w.append("}");
  if (response.truncated) {
    static constexpr std::string_view fallback = "{\"error\":\"response_too_large\"}";
    response = {};
    std::memcpy(response.bytes.data(), fallback.data(), fallback.size());
    response.size = fallback.size();
    response.truncated = true;
  }
  return response;
}

bool FakeExecutionPort::start(std::uint64_t id, const Call& call) noexcept {
  if (mode_ == Mode::StartFailure || active_id_ != 0) return false;
  active_id_ = id; active_call_ = call; polls_ = 0; cancel_seen_ = false; return true;
}

PortResult FakeExecutionPort::poll(std::uint64_t id) noexcept {
  if (id != active_id_ || cancel_seen_) return {PortState::Failed, PortError::Protocol};
  ++polls_;
  if (mode_ == Mode::NeverCompletes || polls_ == 1) return {PortState::Running, PortError::None};
  if (mode_ == Mode::ExecutionFailure) return {PortState::Failed, PortError::Execution};
  PortResult out{PortState::Succeeded, PortError::None};
  if (active_call_.tool == Tool::PhotoCapture) std::snprintf(out.asset_id, sizeof(out.asset_id), "fake-photo-camera-%u", active_call_.camera);
  else if (active_call_.tool == Tool::DeviceStatus) { out.wifi_connected = true; out.battery_percent = 73; }
  else {
    const std::uint8_t count = mode_ == Mode::OversizedScan ? 8 : 3;
    out.ssid_count = count;
    for (std::uint8_t i = 0; i < count; ++i) std::snprintf(out.ssids[i].data(), out.ssids[i].size(), "fake-network-%u-xxxxxxxxxxxx", i);
  }
  return out;
}

void FakeExecutionPort::cancel(std::uint64_t id) noexcept { if (id == active_id_) cancel_seen_ = true; }

}  // namespace velavision::tools
