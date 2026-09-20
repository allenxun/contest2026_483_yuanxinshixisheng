#include "mock_wifi_task.hpp"
#include <iostream>
using namespace voice;
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(0)
int main(){try{
 std::atomic_bool stop{false};MockWifiTask task;
 CHECK(!task.handle(3,"uninterpreted",stop).empty());
 CHECK(task.seen==std::vector<wb_status>({WB_RECEIVED,WB_CONNECTING,WB_IP_READY}));
 CHECK(task.broker.radio==WB_OWNED);task.close();CHECK(task.broker.radio==WB_FREE);
 wb_broker b{};wb_init(&b,0,1);auto r=wb_begin(&b,1,"x",1,"password",8,0,100);
 CHECK(r.status==WB_RECEIVED);wb_job j{};CHECK(wb_take_job(&b,&j,1));wb_job_clear(&j);
 wb_cancel(&b,1,r.id,2);CHECK(b.radio==WB_DRAINING);
 CHECK(wb_begin(&b,2,"y",1,"password",8,3,100).status==WB_BUSY);
 wb_done d{};d.owner=1;d.id=r.id;d.sequence=1;d.success=1;d.authenticated=1;
 d.dhcp=1;d.link_up=1;d.ip[0]=192;d.ip[1]=0;d.ip[2]=2;d.ip[3]=1;
 wb_complete(&b,&d,4);CHECK(b.radio==WB_DRAINING);
 d.sequence=2;d.worker_exited=1;wb_complete(&b,&d,5);CHECK(b.radio==WB_DRAINING);
 d.sequence=3;d.link_up=0;d.success=0;wb_complete(&b,&d,6);CHECK(b.radio==WB_FREE);
 CHECK(wb_poll(&b,1,r.id).status==WB_CANCELLED);
 MockWifiTask fail(true);bool caught=false;try{fail.handle(5,"x",stop);}catch(...){caught=true;}
 CHECK(caught);fail.close();CHECK(fail.broker.radio==WB_FREE);
 std::cout<<"mock_wifi_receipt_connecting_ip_failure_cancel_drain=PASS\n";return 0;
 }catch(const std::exception& e){std::cerr<<e.what();return 1;}}
