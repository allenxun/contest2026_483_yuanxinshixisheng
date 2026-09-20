#pragma once
#include "voicelink/ports.hpp"
extern "C" {
#include "wifi_scan.h"
}
namespace voicelink {
// Service and dispatcher outlive this object. No pump, hardware or global BLE access.
class SharedWifiPort final : public WifiPort {
 public:
  SharedWifiPort(wd_dispatch& d, ws_service& s, std::uint64_t timeout_ms=30000)
    : d_(d), s_(s), timeout_(timeout_ms) {}
  ScanResult beginScan() override;
  ScanResult pollScan(std::uint64_t) override;
  void cancelScan(std::uint64_t) noexcept override;
  ConnectResult beginConnect(const std::string&,const char*,std::size_t) noexcept override;
  ConnectResult pollConnect(std::uint64_t) noexcept override;
  void cancelConnect(std::uint64_t) noexcept override;
 private:
  wd_dispatch& d_; ws_service& s_; std::uint64_t timeout_;
};
}
