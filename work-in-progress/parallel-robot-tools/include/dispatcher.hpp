#pragma once
#include <array>
#include <cstdint>
#include <limits>
#include <optional>
#include <variant>

namespace robot {
// Software ledger only. No backend, I/O, credentials, model, or actuator calls.
enum class Tool { Capabilities, WifiStatus, GimbalTarget, Photo, WifiScan, WifiConnect };
enum class State { Requested, Accepted, Running, Completed, Failed, Cancelled };
enum class Error { None, Invalid, Unsupported, Disabled, Busy, Timeout, Clock, Exhausted, Backend };
struct NoArgs {};
struct Target { int x, y; };
using Args = std::variant<NoArgs, Target>;
struct Request { std::uint64_t owner; Tool tool; Args args; std::uint64_t ttlMs=1000; };
struct Key { std::uint64_t owner=0, id=0; };
inline bool operator==(Key a, Key b) { return a.owner==b.owner && a.id==b.id; }
struct Validated { Request request; State state=State::Requested; };
struct Validation { Error error; std::optional<Validated> call; };
inline Validation validate(const Request& r) {
  if(!r.owner || r.ttlMs==0 || r.ttlMs>30000) return {Error::Invalid,{}};
  switch(r.tool) {
    case Tool::Capabilities: case Tool::WifiStatus:
      if(!std::holds_alternative<NoArgs>(r.args)) return {Error::Invalid,{}};
      return {Error::None,Validated{r}};
    case Tool::GimbalTarget: {
      const auto* t=std::get_if<Target>(&r.args);
      // Existing gimbal_link_adopt bounds; never enables an actuator.
      if(!t || t->x < -800 || t->x > 800 || t->y < -120 || t->y > 1030)
        return {Error::Invalid,{}};
      return {Error::Disabled,{}};
    }
    default: return {Error::Unsupported,{}};
  }
}
struct Capabilities {
  bool queryValidation=true;
  bool deviceAdapterBound=false;
  bool actuatorsEnabled=false;
};
// connected means trusted service confirms authentication AND DHCP/IP readiness;
// neither L2 association nor address syntax alone establishes it. Not internet proof.
// Adapter is absent here; tests inject synthetic snapshots only.
struct WifiStatus { bool connected; std::array<std::uint8_t,4> ipv4; };
using Payload = std::variant<std::monostate, Capabilities, WifiStatus>;
enum class EventKind { Started, Completed, Failed };
// Trusted adapter boundary only; never construct from language-model output.
struct DeviceEvent { Key key; Tool tool; EventKind kind; Payload payload; };
struct Record {
  Key key; Tool tool; State state; Error error; Payload payload;
  std::uint64_t start, ttl; bool taken=false;
};
struct Admission { Error error; std::optional<Key> key; };
struct Call { Key key; Tool tool; }; // No function pointer or executable command.
class Dispatcher {
 public:
  explicit Dispatcher(std::uint64_t firstId=1):next_(firstId) {}
  // Serialized caller required. Monotonic caller clock; no threads are owned.
  Admission submit(const Request& request, std::uint64_t now) {
    tick(now);
    if(clockFault_) return {Error::Clock,{}};
    const auto v=validate(request);
    if(v.error!=Error::None) return {v.error,{}};
    if(!next_) return {Error::Exhausted,{}};
    for(auto& s:slots_) if(!s) {
      const Key key{request.owner,next_};
      next_=next_==std::numeric_limits<std::uint64_t>::max()?0:next_+1;
      s=Record{key,request.tool,State::Accepted,Error::None,{},now,request.ttlMs,false};
      return {Error::None,key};
    }
    return {Error::Busy,{}};
  }
  std::optional<Call> take(Key key,std::uint64_t now) {
    tick(now);auto* s=find(key);
    if(!s || s->state!=State::Accepted || s->taken) return {};
    s->taken=true;return Call{s->key,s->tool};
  }
  bool event(const DeviceEvent& e,std::uint64_t now) {
    tick(now);auto* s=find(e.key);
    if(!s || !s->taken || s->tool!=e.tool || terminal(s->state)) return false;
    if(e.kind==EventKind::Started) {
      if(s->state!=State::Accepted || !std::holds_alternative<std::monostate>(e.payload))return false;
      s->state=State::Running;return true;
    }
    if(e.kind==EventKind::Failed) {
      if(!std::holds_alternative<std::monostate>(e.payload))return false;
      s->state=State::Failed;s->error=Error::Backend;return true;
    }
    if(e.kind!=EventKind::Completed || s->state!=State::Running)return false;
    if(s->tool==Tool::Capabilities) {
      const auto* p=std::get_if<Capabilities>(&e.payload);
      if(!p || p->deviceAdapterBound || p->actuatorsEnabled || !p->queryValidation)return false;
    } else {
      const auto* p=std::get_if<WifiStatus>(&e.payload);
      if(!p)return false;
      const bool zero=p->ipv4==std::array<std::uint8_t,4>{};
      if((p->connected && (zero || p->ipv4[0]==0 || p->ipv4[0]==127 ||
          p->ipv4[0]>=224 || (p->ipv4[0]==169 && p->ipv4[1]==254))) ||
          (!p->connected && !zero))return false;
    }
    s->state=State::Completed;s->payload=e.payload;return true;
  }
  // Cancels interest in a read-only query, NOT any physical device operation.
  bool cancel(Key key,std::uint64_t now) {
    tick(now);auto* s=find(key);if(!s)return false;
    if(s->state==State::Cancelled)return true;
    if(terminal(s->state))return false;
    s->state=State::Cancelled;return true;
  }
  void tick(std::uint64_t now) {
    if(seen_ && now<last_)clockFault_=true;
    seen_=true;last_=now;
    for(auto& s:slots_) if(s && !terminal(s->state)) {
      if(clockFault_){s->state=State::Failed;s->error=Error::Clock;}
      else if(now-s->start>=s->ttl){s->state=State::Failed;s->error=Error::Timeout;}
    }
  }
  std::optional<Record> inspect(Key key)const {
    for(const auto& s:slots_)if(s && s->key==key)return s;
    return {};
  }
  bool release(Key key) {
    for(auto& s:slots_)if(s && s->key==key && terminal(s->state)){s.reset();return true;}
    return false;
  }
 private:
  static bool terminal(State s){return s==State::Completed || s==State::Failed || s==State::Cancelled;}
  Record* find(Key key){for(auto& s:slots_)if(s && s->key==key)return &*s;return nullptr;}
  std::array<std::optional<Record>,8> slots_{};
  std::uint64_t next_,last_=0;bool seen_=false,clockFault_=false;
};
} // namespace robot
