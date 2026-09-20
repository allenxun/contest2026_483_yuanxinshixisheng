#include "dispatcher.hpp"
#include <iostream>
#include <cstdlib>
using namespace robot;
static unsigned checks=0;
#define CHECK(x) do { ++checks; if(!(x)){std::cerr<<"FAIL line "<<__LINE__<<": "<<#x<<'\n';std::exit(1);} } while(false)
struct FakeBackend {
 static DeviceEvent start(Call c){return {c.key,c.tool,EventKind::Started,{}};}
 static DeviceEvent wifi(Call c){return {c.key,c.tool,EventKind::Completed,WifiStatus{true,{10,3,0,214}}};}
};
int main() {
 Request r{7,Tool::WifiStatus,NoArgs{},100};
 CHECK(validate(r).call->state==State::Requested);
 auto bad=r;bad.owner=0;CHECK(validate(bad).error==Error::Invalid);
 for(auto ttl:{0ULL,30001ULL}){bad=r;bad.ttlMs=ttl;CHECK(validate(bad).error==Error::Invalid);}
 bad=r;bad.args=Target{0,0};CHECK(validate(bad).error==Error::Invalid);
 for(auto tool:{Tool::Photo,Tool::WifiScan,Tool::WifiConnect,static_cast<Tool>(999)}) {
   bad=r;bad.tool=tool;CHECK(validate(bad).error==Error::Unsupported);
 }
 for(auto t:{Target{-800,-120},Target{800,1030},Target{0,0}}) {
   bad=r;bad.tool=Tool::GimbalTarget;bad.args=t;CHECK(validate(bad).error==Error::Disabled);
 }
 for(auto t:{Target{-801,0},Target{801,0},Target{0,-121},Target{0,1031}}) {
   bad=r;bad.tool=Tool::GimbalTarget;bad.args=t;CHECK(validate(bad).error==Error::Invalid);
 }
 Dispatcher d;auto a=d.submit(r,0);CHECK(a.error==Error::None);
 auto key=*a.key;CHECK(d.inspect(key)->state==State::Accepted);
 CHECK(!d.release(key));CHECK(!d.take({8,key.id},0));
 CHECK(!d.event({key,Tool::WifiStatus,EventKind::Completed,WifiStatus{true,{10,3,0,214}}},0));
 auto c=*d.take(key,1);CHECK(!d.take(key,1));CHECK(d.inspect(key)->state==State::Accepted);
 CHECK(!d.event(FakeBackend::wifi(c),2));
 auto wrong=FakeBackend::start(c);wrong.key.owner=8;CHECK(!d.event(wrong,2));
 wrong=FakeBackend::start(c);wrong.tool=Tool::Capabilities;CHECK(!d.event(wrong,2));
 CHECK(d.event(FakeBackend::start(c),2));CHECK(d.inspect(key)->state==State::Running);
 CHECK(!d.event(FakeBackend::start(c),2));
 CHECK(!d.event({key,c.tool,EventKind::Completed,Capabilities{}},3));
 CHECK(!d.event({key,c.tool,EventKind::Completed,WifiStatus{true,{}}},3));
 for(auto ip:{std::array<std::uint8_t,4>{127,0,0,1},{169,254,1,2},{224,0,0,1},{255,255,255,255}})
   CHECK(!d.event({key,c.tool,EventKind::Completed,WifiStatus{true,ip}},3));
 CHECK(!d.event({key,c.tool,EventKind::Completed,WifiStatus{false,{10,0,0,1}}},3));
 CHECK(d.event(FakeBackend::wifi(c),4));CHECK(d.inspect(key)->state==State::Completed);
 CHECK(!d.event(FakeBackend::wifi(c),4));CHECK(!d.cancel(key,4));CHECK(d.release(key));
 auto k2=*d.submit(r,4).key;CHECK(k2.id!=key.id);CHECK(!d.event(FakeBackend::wifi(c),4));
 CHECK(!d.cancel({8,k2.id},4));CHECK(d.cancel(k2,4));CHECK(d.cancel(k2,4));CHECK(d.release(k2));
 auto k3=*d.submit(r,5).key;auto c3=*d.take(k3,5);CHECK(d.event(FakeBackend::start(c3),5));
 CHECK(d.cancel(k3,6));CHECK(!d.event(FakeBackend::wifi(c3),6));CHECK(d.inspect(k3)->state==State::Cancelled);
 auto k4=*d.submit(r,10).key;auto c4=*d.take(k4,10);CHECK(d.event(FakeBackend::start(c4),10));
 CHECK(!d.event(FakeBackend::wifi(c4),110));CHECK(d.inspect(k4)->error==Error::Timeout);
 Dispatcher caps;Request cr{1,Tool::Capabilities,NoArgs{},10};auto ck=*caps.submit(cr,0).key;
 auto cc=*caps.take(ck,0);CHECK(caps.event(FakeBackend::start(cc),0));
 CHECK(!caps.event({ck,cc.tool,EventKind::Completed,Capabilities{true,true,false}},0));
 CHECK(caps.event({ck,cc.tool,EventKind::Completed,Capabilities{}},0));
 Dispatcher fail;auto fk=*fail.submit(r,0).key;auto fc=*fail.take(fk,0);
 CHECK(fail.event({fk,fc.tool,EventKind::Failed,{}},0));CHECK(fail.inspect(fk)->error==Error::Backend);
 Dispatcher clock;auto x=*clock.submit(r,10).key;clock.tick(9);CHECK(clock.inspect(x)->error==Error::Clock);
 CHECK(clock.submit(r,11).error==Error::Clock);
 Dispatcher full;for(int i=0;i<8;++i)CHECK(full.submit(r,0).key.has_value());CHECK(full.submit(r,0).error==Error::Busy);
 Dispatcher exhausted(std::numeric_limits<std::uint64_t>::max());CHECK(exhausted.submit(r,0).key.has_value());
 CHECK(exhausted.submit(r,0).error==Error::Exhausted);
 Dispatcher overflow;const auto max=std::numeric_limits<std::uint64_t>::max();
 auto ok=*overflow.submit(r,max-50).key;overflow.tick(max);CHECK(overflow.inspect(ok)->state==State::Accepted);
 // Stress bounded storage, ID reuse prevention, cancellation and stale results.
 Dispatcher stress;
 for(std::uint64_t i=0;i<2000;++i){auto k=*stress.submit(r,i).key;auto call=*stress.take(k,i);
   CHECK(stress.cancel(k,i));CHECK(stress.release(k));CHECK(!stress.event(FakeBackend::wifi(call),i));}
 std::cout<<"PASS "<<checks<<" checks (fake backend only)\n";
}
