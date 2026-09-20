#include "voice_wifi_adapter.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include <atomic>
using namespace voicelink;
static std::atomic<unsigned> checks;
#define C(x) do { ++checks; if(!(x)) {std::fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);std::abort();} }while(0)
struct Fixture {
 wd_dispatch d{}; ws_service s{}; std::mutex mutex; unsigned depth=0, scans=0,stops=0,joins=0;
 uint64_t now=100,id=0;int reject=0,stop_fail=0;wb_job job{};
 static void lock(void*p){auto*f=(Fixture*)p;f->mutex.lock();C(f->depth++==0);}
 static void unlock(void*p){auto*f=(Fixture*)p;C(--f->depth==0);f->mutex.unlock();}
 static uint64_t clock(void*p){return ((Fixture*)p)->now;}
 static int join(void*p,const wb_job*j){auto*f=(Fixture*)p;C(!f->depth);f->joins++;f->job=*j;return 0;}
 static int stop_join(void*p,uint64_t,uint64_t){C(!((Fixture*)p)->depth);return 0;}
 static int scan(void*p,uint64_t id){auto*f=(Fixture*)p;C(!f->depth);f->scans++;f->id=id;C(wd_pump(&f->d)==WD_BUSY);return f->reject;}
 static int stop(void*p,uint64_t id){auto*f=(Fixture*)p;C(!f->depth&&f->id==id);f->stops++;return f->stop_fail;}
 Fixture(bool offline=true){wd_port dp{this,lock,unlock,clock,join,stop_join};C(wd_init(&d,&dp,offline)==0);ws_port sp{this,scan,stop};C(ws_attach(&s,&d,&sp)==0);}
 void pump(){C(wd_pump(&d)==WD_OK);}
 ws_done done(uint64_t t,uint64_t seq=1){return {t,seq,true,true,true,true,true,true,true};}
 void finish(uint64_t t){auto e=done(t);C(ws_post(&s,&e)==WD_OK);pump();}
 sc_record record(unsigned n=1){sc_record r{};r.ssid_len=3;std::memcpy(r.ssid,"AP1",3);r.bssid[0]=2;r.bssid[5]=(uint8_t)n;r.security=2;r.rssi=-40;r.channel=1;return r;}
};
static void ready_and_busy(){
 Fixture f;SharedWifiPort p(f.d,f.s);auto a=p.beginScan();C(a.status==ScanStatus::Received&&a.request_id);
 uint64_t ble;C(ws_ble_begin(&f.s,500,&ble)==WD_BUSY&&ble!=a.request_id);
 C(ws_ble_cancel(&f.s,a.request_id)==WD_FORBIDDEN);f.pump();C(f.scans==1&&f.d.broker.radio==WB_SCAN);
 C(p.pollScan(a.request_id).status==ScanStatus::Scanning);
 uint64_t join;C(wd_ble_begin(&f.d,"AP1",3,"12345678",8,500,&join)==WD_OK);f.pump();wd_view v{};
 C(wd_ble_poll(&f.d,join,&v)==WD_OK&&v.status==WB_BUSY&&f.joins==0);
 auto r=f.record();C(ws_record(&f.s,a.request_id,&r)==SC_OK);f.finish(a.request_id);
 auto result=p.pollScan(a.request_id);C(result.status==ScanStatus::Ready&&result.access_points.size()==1&&result.access_points[0].ssid=="AP1");
 C(f.d.broker.radio==WB_FREE&&f.s.view.held==0);C(ws_record(&f.s,a.request_id,&r)==SC_STALE);
 auto b=p.beginScan();f.pump();C(b.request_id>join);C(ws_record(&f.s,a.request_id,&r)==SC_STALE);
 auto stale=f.done(a.request_id,2);C(ws_post(&f.s,&stale)==WD_UNKNOWN);
 C(result.access_points[0].ssid=="AP1");p.cancelScan(b.request_id);f.pump();f.finish(b.request_id);
}
static void fences(){
 for(unsigned missing=0;missing<5;missing++){
  Fixture f;SharedWifiPort p(f.d,f.s);auto a=p.beginScan();f.pump();p.cancelScan(a.request_id);f.pump();C(f.stops==1);
  auto e=f.done(a.request_id);switch(missing){case 0:e.stop_ok=false;break;case 1:e.close_ok=false;break;case 2:e.worker_exited=false;break;case 3:e.rx_quiescent=false;break;default:e.offline=false;}
  C(ws_post(&f.s,&e)==WD_OK);f.pump();C(f.s.view.held&&f.d.broker.radio==WB_SCAN);
  uint64_t b;C(ws_ble_begin(&f.s,500,&b)==WD_BUSY);C(p.pollScan(a.request_id).status==ScanStatus::Cancelled);
  e=f.done(a.request_id,2);C(ws_post(&f.s,&e)==WD_OK);f.pump();C(!f.s.view.held&&f.d.broker.radio==WB_FREE);
 }
}
static void boundaries(){
 {Fixture f;SharedWifiPort p(f.d,f.s);auto a=p.beginScan();p.cancelScan(a.request_id);f.pump();C(f.scans==0&&p.pollScan(a.request_id).status==ScanStatus::Cancelled);}
 {Fixture f;f.reject=1;SharedWifiPort p(f.d,f.s);auto a=p.beginScan();f.pump();C(p.pollScan(a.request_id).status==ScanStatus::Failed&&!f.s.view.held&&f.d.broker.radio==WB_FREE);}
 {Fixture f;SharedWifiPort p(f.d,f.s,10);auto a=p.beginScan();f.pump();f.now+=10;f.stop_fail=1;f.pump();C(p.pollScan(a.request_id).status==ScanStatus::Timeout&&f.s.view.held&&f.stops==1);f.stop_fail=0;f.pump();C(f.stops==2);f.finish(a.request_id);C(p.pollScan(a.request_id).status==ScanStatus::Timeout);}
 {Fixture f;SharedWifiPort p(f.d,f.s);auto a=p.beginScan();f.pump();f.now--;f.pump();C(p.pollScan(a.request_id).status==ScanStatus::Failed&&f.s.view.held);f.finish(a.request_id);}
 {Fixture f(false);SharedWifiPort p(f.d,f.s);auto a=p.beginScan();f.pump();C(p.pollScan(a.request_id).status==ScanStatus::Busy&&f.scans==0&&f.d.broker.radio==WB_EXTERNAL);}
 {Fixture f;SharedWifiPort p(f.d,f.s);auto a=p.beginScan();f.pump();auto e=f.done(a.request_id);C(ws_post(&f.s,&e)==WD_OK);C(ws_post(&f.s,&e)==WD_FULL);f.pump();C(ws_post(&f.s,&e)==WD_UNKNOWN);}
 {Fixture f;f.d.next_ticket=UINT64_MAX;SharedWifiPort p(f.d,f.s);auto a=p.beginScan();C(a.request_id==UINT64_MAX);auto b=p.beginScan();C(!b.request_id&&b.status==ScanStatus::Failed);}
 {Fixture f;uint64_t id;C(ws_ble_begin(&f.s,500,&id)==WD_OK);f.pump();C(ws_voice_cancel(&f.s,id)==WD_FORBIDDEN);vs_snapshot v{};C(ws_voice_poll(&f.s,id,&v)==WD_FORBIDDEN);f.finish(id);C(ws_ble_poll(&f.s,id,&v)==WD_OK&&v.state==VS_DONE);}
 {Fixture f;SharedWifiPort p(f.d,f.s);auto a=p.beginScan();f.pump();for(unsigned i=1;i<=65;i++){auto r=f.record(i);C(ws_record(&f.s,a.request_id,&r)==(i<=64?SC_OK:SC_FULL));}f.finish(a.request_id);C(f.s.view.count==64&&f.s.view.truncated&&p.pollScan(a.request_id).access_points.size()==64);}
}
static void connection(){
 Fixture f;SharedWifiPort p(f.d,f.s);auto a=p.beginConnect("AP1","12345678",8);C(a.status==ConnectStatus::CredentialsReceived);f.pump();C(p.pollConnect(a.request_id).status==ConnectStatus::Connecting&&f.joins==1);
 auto scan=p.beginScan();f.pump();C(p.pollScan(scan.request_id).status==ScanStatus::Busy);
 wd_event e{};e.kind=WD_PROGRESS;e.done={f.job.owner,f.job.id,1,1,1,1,1,1,{10,3,0,214}};
 C(wd_post(&f.d,&e)==WD_OK);f.pump();C(p.pollConnect(a.request_id).status==ConnectStatus::Connecting);
 e.kind=WD_COMPLETION;e.done.sequence=2;C(wd_post(&f.d,&e)==WD_OK);f.pump();auto ip=p.pollConnect(a.request_id);C(ip.status==ConnectStatus::IpReady&&ip.ipv4=="10.3.0.214");
 scan=p.beginScan();f.pump();C(p.pollScan(scan.request_id).status==ScanStatus::Unsupported&&f.scans==0&&f.d.broker.radio==WB_OWNED);
 C(wd_ble_release(&f.d,a.request_id)==WD_FORBIDDEN);C(wd_voice_release(&f.d,a.request_id)==WD_OK);f.pump();
 e.done.sequence=3;e.done.link_up=0;e.done.success=0;C(wd_post(&f.d,&e)==WD_OK);f.pump();C(f.d.broker.radio==WB_FREE);
 scan=p.beginScan();f.pump();e.done.sequence=4;C(wd_post(&f.d,&e)==WD_OK);f.pump();C(f.d.broker.radio==WB_SCAN);f.finish(scan.request_id);
}
static void races(){
 for(unsigned round=0;round<100;round++) {
  Fixture f;uint64_t a=0,b=0;wd_rc ra,rb;
  std::thread ta([&]{ra=ws_voice_begin(&f.s,500,&a);});
  std::thread tb([&]{rb=ws_ble_begin(&f.s,500,&b);});ta.join();tb.join();
  C(a&&b&&a!=b);C((ra==WD_OK&&rb==WD_BUSY)||(rb==WD_OK&&ra==WD_BUSY));
  f.pump();C(f.scans==1);f.finish(ra==WD_OK?a:b);
 }
}
static void invalid_ip_and_text(){
 for(unsigned bad=0;bad<5;bad++) {
  Fixture f;SharedWifiPort p(f.d,f.s);auto a=p.beginConnect("AP1","12345678",8);f.pump();
  wd_event e{};e.kind=WD_COMPLETION;e.done={f.job.owner,f.job.id,1,1,1,1,1,1,{10,3,0,214}};
  switch(bad){case 0:e.done.authenticated=0;break;case 1:e.done.dhcp=0;break;case 2:e.done.worker_exited=0;break;case 3:e.done.ip[0]=0;break;default:e.done.ip[0]=127;}
  C(wd_post(&f.d,&e)==WD_OK);f.pump();C(p.pollConnect(a.request_id).status!=ConnectStatus::IpReady&&f.d.broker.radio==WB_DRAINING);
 }
 for(unsigned bad=0;bad<3;bad++) {
  Fixture f;SharedWifiPort p(f.d,f.s);auto a=p.beginScan();f.pump();auto r=f.record();r.ssid[1]=bad==0?0:bad==1?0xff:0xc0;
  C(ws_record(&f.s,a.request_id,&r)==SC_OK);f.finish(a.request_id);C(p.pollScan(a.request_id).status==ScanStatus::Failed);
 }
}
int main(){races();invalid_ip_and_text();ready_and_busy();fences();boundaries();connection();std::printf("PASS checks=%u; real candidate functions, injected mock hardware only; no radio/IP acceptance\n",checks.load());}
