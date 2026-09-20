#pragma once
#include <atomic>
#include <cstdint>
#include <limits>
#include <optional>
#include <string>
#include <stdexcept>

namespace voice {
enum class State { Idle, Listening, Recognizing, Handling, Speaking, Cancelling, Error };
enum class Op { ReadWav, Asr, Task, Tts, Release };
enum class Policy { ReleaseBeforeTask, ReleaseBeforeTts };
enum class Outcome { None, Success, Cancelled, Timeout, Failure, ClockError };
struct Config {
 Policy policy=Policy::ReleaseBeforeTask;
 std::uint64_t stageMs=30000, totalMs=90000;
 std::size_t maxTextBytes=8192;
};
struct Command { std::uint64_t transaction, operation; Op kind; };
struct Event {
 Event(Command c,bool success=true,std::string value={},bool freed=false):
  command(c),ok(success),text(std::move(value)),released(freed){}
 Command command;
 bool ok=true;
 std::string text;
 // Only trusted worker after synchronous destruction AND TaskPort quiescence.
 bool released=false;
};
// Serialized coordinator only; owns no backend resources. One outstanding command.
// Driver owns worker and MUST stop/join/close before destroying coordinator.
class Machine {
 public:
 explicit Machine(Config config={}, std::uint64_t firstId=1):cfg_(config),next_(firstId) {
  if(!cfg_.stageMs || !cfg_.totalMs || !cfg_.maxTextBytes || !firstId)
   throw std::invalid_argument("invalid configuration");
 }
 bool start(std::uint64_t now) {
  if(state_!=State::Idle || !next_ || clockFault_)return false;
  id_=next_;next_=next_==std::numeric_limits<std::uint64_t>::max()?0:next_+1;
  sequence_=0; start_=last_=stage_=now; outcome_=Outcome::None;
  transcript_.clear(); reply_.clear();state_=State::Listening;queue(Op::ReadWav);return true;
 }
 std::optional<Command> take() {
  if(!pending_ || running_)return {};
  running_=true;return pending_;
 }
 void tick(std::uint64_t now) {
  if(state_==State::Idle || state_==State::Error)return;
  if(now<last_){clockFault_=true;cancel(Outcome::ClockError);return;}
  last_=now;
  if(state_!=State::Cancelling && (now-start_>=cfg_.totalMs || now-stage_>=cfg_.stageMs))
   cancel(Outcome::Timeout);
 }
 void cancel(Outcome why=Outcome::Cancelled) {
  if(state_==State::Idle || state_==State::Error || state_==State::Cancelling)return;
  outcome_=why;state_=State::Cancelling;
  if(!running_)queueRelease(After::Cancelled);
 }
 bool complete(const Event& event,std::uint64_t now) {
  tick(now); // deadline wins a simultaneous result
  if(!running_ || !pending_ || event.command.transaction!=id_ ||
     event.command.operation!=pending_->operation || event.command.kind!=pending_->kind)return false;
  running_=false;const auto op=pending_->kind;pending_.reset();
  if(state_==State::Cancelling) {
   if(op==Op::Release && event.ok && event.released)finishCancelled();
   else queueRelease(After::Cancelled);
   return true;
  }
  if(!event.ok || event.text.size()>cfg_.maxTextBytes ||
     (op==Op::Release && !event.released)) {
   cancel(Outcome::Failure);return true;
  }
  stage_=last_;
  switch(op) {
   case Op::ReadWav:state_=State::Recognizing;queue(Op::Asr);break;
   case Op::Asr:
    if(event.text.empty()){cancel(Outcome::Failure);break;}
    transcript_=event.text;
    if(cfg_.policy==Policy::ReleaseBeforeTask)queueRelease(After::Task);
    else {state_=State::Handling;queue(Op::Task);} break;
   case Op::Task:
    if(event.text.empty()){cancel(Outcome::Failure);break;}
    reply_=event.text;queueRelease(After::Tts);break;
   case Op::Tts:queueRelease(After::Success);break;
   case Op::Release:
    if(after_==After::Task){state_=State::Handling;queue(Op::Task);}
    else if(after_==After::Tts){state_=State::Speaking;queue(Op::Tts);}
    else {state_=State::Idle;outcome_=Outcome::Success;}
    break;
  }
  return true;
 }
 bool resetError() {if(state_!=State::Error || clockFault_)return false;state_=State::Idle;return true;}
 State state()const{return state_;}
 Outcome outcome()const{return outcome_;}
 bool stopRequested()const{return state_==State::Cancelling;}
 bool running()const{return running_;}
 std::uint64_t id()const{return id_;}
 const std::string& transcript()const{return transcript_;}
 const std::string& reply()const{return reply_;}
 private:
 enum class After {Task,Tts,Success,Cancelled};
 void queue(Op op){pending_=Command{id_,++sequence_,op};}
 void queueRelease(After after){after_=after;queue(Op::Release);}
 void finishCancelled(){state_=outcome_==Outcome::Cancelled?State::Idle:State::Error;}
 Config cfg_;std::uint64_t next_,id_=0,sequence_=0,start_=0,last_=0,stage_=0;
 State state_=State::Idle;Outcome outcome_=Outcome::None;After after_=After::Success;
 bool running_=false,clockFault_=false;std::optional<Command> pending_;
 std::string transcript_,reply_;
};
// Blocking worker boundary. Implementations must observe stop/deadlines at bounded
// checkpoints, retain ownership until quiescence, and never report fake success.
class TaskPort {
 public:
 virtual ~TaskPort()=default;
 virtual std::string handle(std::uint64_t,const std::string&,const std::atomic_bool&)=0;
 virtual void close() noexcept=0; // synchronous quiescence; may block
};
}
