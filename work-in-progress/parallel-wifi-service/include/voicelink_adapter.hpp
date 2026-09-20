#pragma once
#include "wifi_broker.h"
#include "voicelink/ports.hpp"
#include <cstdio>
// Service task only. Do not call directly from a concurrent ASR/BLE thread.
class BrokerWifiPort final : public voicelink::WifiPort {
 public:
  BrokerWifiPort(wb_broker& b, voicelink::ClockPort& clock, std::uint64_t owner)
      : b_(b), clock_(clock), owner_(owner) {}
  voicelink::ScanResult scan() override {
    return {voicelink::IoStatus::FatalError, {}, -38}; // no fake scan success
  }
  voicelink::ConnectResult beginConnect(const std::string& ssid, const char* pw,
                                      std::size_t n) noexcept override {
    return convert(wb_begin(&b_,owner_,ssid.data(),ssid.size(),pw,n,clock_.nowMs(),30000));
  }
  voicelink::ConnectResult pollConnect(std::uint64_t id) noexcept override {
    wb_tick(&b_,clock_.nowMs()); return convert(wb_poll(&b_,owner_,id));
  }
  void cancelConnect(std::uint64_t id) noexcept override {
    wb_cancel(&b_,owner_,id,clock_.nowMs());
  }
 private:
  static voicelink::ConnectResult convert(wb_result r) noexcept {
    using S=voicelink::ConnectStatus;
    voicelink::ConnectResult out; out.request_id=r.id;
    switch(r.status) {
      case WB_RECEIVED: out.status=S::CredentialsReceived; break;
      case WB_CONNECTING: out.status=S::Connecting; break;
      case WB_IP_READY: {
        char ip[16];
        std::snprintf(ip,sizeof(ip),"%u.%u.%u.%u",r.ip[0],r.ip[1],r.ip[2],r.ip[3]);
        // Allocation failure must not escape the WifiPort noexcept boundary.
        try { out.ipv4=ip; out.status=S::IpReady; }
        catch(...) { out.status=S::Failed; out.error_code=-12; }
        break;
      }
      case WB_BUSY: out.status=S::Busy; break;
      case WB_CANCELLED: out.status=S::Cancelled; break;
      case WB_TIMEOUT: out.status=S::Timeout; break;
      case WB_UNSUPPORTED: out.status=S::Unsupported; break;
      default: out.status=S::Failed; out.error_code=-static_cast<int>(r.status)-1; break;
    }
    return out;
  }
  wb_broker& b_; voicelink::ClockPort& clock_; std::uint64_t owner_;
};
