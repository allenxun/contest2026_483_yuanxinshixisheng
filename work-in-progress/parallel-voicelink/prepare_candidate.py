"""Regenerate candidate core from the immutable input snapshot (local only)."""
from pathlib import Path

root = Path(__file__).resolve().parent
def read(name):
    return (root / 'input' / name).read_text(encoding='utf-8-sig')
def write(name, data):
    (root / name).write_text(data, encoding='utf-8')

s = read('include/voicelink/types.hpp')
s = s.replace('  Completed,', '  CredentialsReceived,\n  ConnectingWifi,\n  Completed,')
s = s.replace('  std::size_t max_networks{5};', '  std::size_t max_networks{5};\n  std::uint64_t connect_timeout_ms{30000};')
a, b = s.index('enum class ConnectStatus'), s.index('struct Context')
s = s[:a] + '''// Receipt/association is not IP readiness. No legacy synchronous Ok status.
enum class ConnectStatus {
  CredentialsReceived, Connecting, IpReady, WrongPassword, Timeout,
  NetworkNotFound, Failed, Busy, Unsupported, Cancelled
};
struct ConnectResult {
  ConnectStatus status{ConnectStatus::Failed};
  int error_code{};
  std::uint64_t request_id{};
  std::string ipv4;
};

''' + s[b:]
write('include/voicelink/types.hpp', s)
s = read('include/voicelink/ports.hpp')
a, b = s.index('  // password may'), s.index('\n};', s.index('  // password may'))
s = s[:a] + '''  // Connection methods are bounded/nonblocking, noexcept, never call Controller.
  // beginConnect must copy needed credentials before returning, never retain
  // the caller pointer or log secrets; erase its copy on completion/cancel.
  // IDs are unique for this port lifetime, including rejected attempts.
  virtual ConnectResult beginConnect(const std::string& ssid, const char* password,
                                    std::size_t password_len) noexcept = 0;
  virtual ConnectResult pollConnect(std::uint64_t request_id) noexcept = 0;
  // Cancel only this transaction; idempotent. Never disconnect another client.
  virtual void cancelConnect(std::uint64_t request_id) noexcept = 0;
''' + s[b:]
s = s.replace('class TextInputPort', '''class ClockPort {
 public:
  virtual ~ClockPort() = default;
  virtual std::uint64_t nowMs() const noexcept = 0; // monotonic milliseconds
};

class TextInputPort''')
write('include/voicelink/ports.hpp', s)
s = read('include/voicelink/controller.hpp')
s = s.replace('WifiPort& wifi, Config', 'WifiPort& wifi, ClockPort& clock, Config')
s = s.replace('  void start();', '  void start();\n  void poll(); // schedule independently of ASR (recommended <= 50 ms)\n  void cancel();')
s = s.replace('  void repeat(', '  void applyConnectResult(const ConnectResult& result);\n  void cancelPending();\n  void repeat(')
s = s.replace('  Config config_;', '  ClockPort& clock_;\n  std::uint64_t request_id_{};\n  std::uint64_t started_ms_{};\n  Config config_;')
write('include/voicelink/controller.hpp', s)
s = read('src/core.cpp')
s = s.replace('  value.shrink_to_fit();', '  // Keep reserved storage: no allocation/reallocation while entering secrets.')
s = s.replace('WifiPort& wifi, Config config)', 'WifiPort& wifi, ClockPort& clock, Config config)')
s = s.replace('wifi_(wifi), config_', 'wifi_(wifi), clock_(clock), config_')
s = s.replace('  if (config_.min_password_length', '  config_.max_networks = std::min<std::size_t>(5, config_.max_networks);\n  config_.max_password_length = std::min<std::size_t>(63, config_.max_password_length);\n  context_.password.reserve(config_.max_password_length);\n  if (config_.min_password_length', 1)
s = s.replace('Controller::~Controller() { wipePassword(); }', 'Controller::~Controller() { cancelPending(); wipePassword(); }')
s = s.replace('  context_ = Context{};', '  cancelPending();\n  context_.candidates.clear();\n  context_.selected_index.reset();\n  context_.password_mode = PasswordMode::Lower;')
s = s.replace('    default:\n      return;', '    case State::CredentialsReceived:\n    case State::ConnectingWifi:\n      if (isCancel(text)) cancel();\n      return;\n    default:\n      return;', 1)
s = s.replace('      // Input source exhausted: wipe secrets and signal the caller to exit.\n      wipePassword();', '      cancelPending();\n      context_.state = State::Idle;\n      wipePassword();')
s = s.replace('    case IoStatus::FatalError:\n      wipePassword();', '    case IoStatus::FatalError:\n      cancelPending();\n      wipePassword();')
a, b = s.index('  const auto& ap =', s.index('void Controller::tryConnect')), s.index('\nvoid Controller::repeat')
s = s[:a] + '''  const auto& ap = context_.candidates[*context_.selected_index];
  started_ms_ = clock_.nowMs();
  const auto result = wifi_.beginConnect(ap.ssid, password, password_len);
  wipePassword();
  request_id_ = result.request_id;
  if (!request_id_) {
    setTerminal(State::Error, "连接接口未提供事务编号");
    return;
  }
  applyConnectResult(result);
}

void Controller::cancelPending() {
  const auto id = request_id_;
  request_id_ = 0;
  if (id) wifi_.cancelConnect(id);
}

void Controller::cancel() {
  cancelPending();
  setTerminal(State::Idle, "已取消配置");
}

void Controller::poll() {
  if (!request_id_) return;
  // Timeout wins at the exact deadline, including a simultaneously ready event.
  if (clock_.nowMs() - started_ms_ >= config_.connect_timeout_ms) {
    const auto id = request_id_;
    cancelPending();
    applyConnectResult({ConnectStatus::Timeout, 0, id, {}});
    return;
  }
  auto result = wifi_.pollConnect(request_id_);
  if (result.request_id != request_id_) return; // stale/foreign event
  applyConnectResult(result);
}

namespace {
bool usableIpv4(const std::string& ip) {
  unsigned octets[4]{};
  std::size_t pos = 0;
  for (unsigned i = 0; i < 4; ++i) {
    std::size_t digits = 0;
    while (pos < ip.size() && ip[pos] >= '0' && ip[pos] <= '9') {
      if (++digits > 3) return false;
      octets[i] = octets[i] * 10 + static_cast<unsigned>(ip[pos++] - '0');
    }
    if (!digits || octets[i] > 255) return false;
    if (i < 3 && (pos == ip.size() || ip[pos++] != '.')) return false;
  }
  return pos == ip.size() && octets[0] != 0 && octets[0] != 127 &&
         octets[0] < 224 && !(octets[0] == 169 && octets[1] == 254);
}
}

void Controller::applyConnectResult(const ConnectResult& result) {
  if (result.status == ConnectStatus::CredentialsReceived) {
    if (context_.state != State::ConnectingWifi &&
        context_.state != State::CredentialsReceived) {
      context_.state = State::CredentialsReceived;
      repeat("已收到凭据，等待联网结果");
    }
    return;
  }
  if (result.status == ConnectStatus::Connecting) {
    if (context_.state != State::ConnectingWifi) {
      context_.state = State::ConnectingWifi;
      repeat("正在连接网络");
    }
    return;
  }
  if (result.status == ConnectStatus::IpReady && usableIpv4(result.ipv4)) {
    request_id_ = 0; // successful transaction already released by port
    setTerminal(State::Completed, "已连接到" +
                context_.candidates[*context_.selected_index].ssid);
    return;
  }
  cancelPending(); // terminal failures must release provider-side state
  wipePassword();
  context_.password_mode = PasswordMode::Lower;
  const bool secured = context_.selected_index &&
      context_.candidates[*context_.selected_index].secured;
  context_.state = secured ? State::EnteringPassword : State::WaitingNetworkChoice;
  context_.grammar = secured ? Grammar::PasswordToken : Grammar::NetworkSelection;
  switch (result.status) {
    case ConnectStatus::WrongPassword: repeat("密码错误，请重新输入"); break;
    case ConnectStatus::Timeout: repeat("连接超时，请重试"); break;
    case ConnectStatus::Busy: repeat("网络服务忙，请稍后重试"); break;
    case ConnectStatus::Unsupported: repeat("暂不支持该网络，请重新选择网络"); break;
    case ConnectStatus::NetworkNotFound: repeat("找不到该网络，请重新选择网络"); break;
    case ConnectStatus::Cancelled: setTerminal(State::Idle, "已取消配置"); break;
    default: repeat("连接失败，请重试"); break;
  }
}
''' + s[b:]
s = s.replace('''        if (!tts_.speak(config_.greeting)) {
          context_.state = State::Error;
          return;
        }''', '''        repeat(config_.greeting);
        if (context_.state == State::Error) return;''')
s = s.replace('  tts_.stop();\n}', '''#if defined(__cpp_exceptions) || defined(__EXCEPTIONS)
  try { tts_.stop(); } catch (...) { context_.state = State::Error; }
#else
  tts_.stop();
#endif
}''', 1)
s = s.replace('''  tts_.stop();
  if (!tts_.speak(text)) context_.state = State::Error;''', '''  bool spoken = false;
#if defined(__cpp_exceptions) || defined(__EXCEPTIONS)
  try {
    tts_.stop();
    spoken = tts_.speak(text);
  } catch (...) { spoken = false; }
#else
  tts_.stop();
  spoken = tts_.speak(text);
#endif
  if (!spoken) {
    cancelPending();
    wipePassword();
    context_.state = State::Error;
  }''')
write('src/core.cpp', s)
