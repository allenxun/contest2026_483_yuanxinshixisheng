#include "voicelink_adapter.hpp"
#include <cassert>
#include <iostream>
struct Clock:voicelink::ClockPort{std::uint64_t now{};std::uint64_t nowMs()const noexcept override{return now;}};
int main(){
  wb_broker b;wb_init(&b,0,1);Clock c;BrokerWifiPort ble(b,c,1),voice(b,c,2);
  auto a=ble.beginConnect("TestNet","testpass",8);
  auto v=voice.beginConnect("TestNet","testpass",8);
  assert(a.status==voicelink::ConnectStatus::CredentialsReceived);
  assert(v.status==voicelink::ConnectStatus::Busy && v.request_id!=a.request_id);
  voice.cancelConnect(a.request_id);assert(b.radio==WB_QUEUED);
  wb_job j;assert(wb_take_job(&b,&j,0));wb_job_clear(&j);
  wb_done d{};d.owner=1;d.id=a.request_id;d.sequence=1;d.success=d.authenticated=d.dhcp=d.worker_exited=d.link_up=1;
  d.ip[0]=192;d.ip[2]=2;d.ip[3]=7;wb_complete(&b,&d,0);
  auto online=ble.pollConnect(a.request_id);assert(online.status==voicelink::ConnectStatus::IpReady && online.ipv4=="192.0.2.7");
  ble.cancelConnect(a.request_id);assert(b.radio==WB_OWNED);
  assert(voice.scan().status==voicelink::IoStatus::FatalError);
  std::cout<<"adapter scenarios passed (mock only)\n";
}
