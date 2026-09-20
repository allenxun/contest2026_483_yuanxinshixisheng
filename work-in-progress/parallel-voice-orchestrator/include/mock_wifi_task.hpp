#pragma once
#include "orchestrator.hpp"
#include "wifi_broker.h"
#include <vector>
namespace voice {
// Example ONLY. Fake credentials, fake radio, synthetic IP; no hardware/network.
class MockWifiTask final:public TaskPort {
 public:
 explicit MockWifiTask(bool fail=false):fail_(fail){wb_init(&broker,0,1);}
 std::string handle(std::uint64_t owner,const std::string&,const std::atomic_bool& stop) override {
  if(stop.load())throw std::runtime_error("cancelled");
  const auto r=wb_begin(&broker,owner,"mock",4,"mockpass",8,++now,100);
  seen.push_back(r.status);if(r.status!=WB_RECEIVED)throw std::runtime_error("broker busy");
  wb_job job{};if(!wb_take_job(&broker,&job,++now))throw std::runtime_error("worker missing");
  wb_job_clear(&job);seen.push_back(wb_poll(&broker,owner,r.id).status);
  wb_done d{};d.owner=owner;d.id=r.id;d.sequence=1;
  d.success=!fail_;d.authenticated=!fail_;d.dhcp=!fail_;d.worker_exited=1;d.link_up=!fail_;
  d.ip[0]=192;d.ip[1]=0;d.ip[2]=2;d.ip[3]=1; // RFC documentation address
  if(stop.load())wb_cancel(&broker,owner,r.id,++now);
  wb_complete(&broker,&d,++now);auto result=wb_poll(&broker,owner,r.id);seen.push_back(result.status);
  if(result.status!=WB_IP_READY)throw std::runtime_error("mock connection failed/cancelled");
  return "模拟网络连接成功。";
 }
 void close()noexcept override {
  const auto a=broker.active;
  if(broker.radio==WB_OWNED)wb_release(&broker,a.owner,a.id,++now);
  else if(broker.radio==WB_RUNNING || broker.radio==WB_QUEUED)wb_cancel(&broker,a.owner,a.id,++now);
  if(broker.radio==WB_DRAINING){wb_done d{};d.owner=a.owner;d.id=a.id;
   d.sequence=broker.event_sequence+1;d.worker_exited=1;wb_complete(&broker,&d,++now);}
 }
 ~MockWifiTask(){close();}
 wb_broker broker{};std::vector<wb_status> seen;
 private:bool fail_;std::uint64_t now=0;
};
}
