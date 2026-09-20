#include "orchestrator.hpp"
#include <iostream>
#include <limits>
using namespace voice;
static int checks=0;
#define CHECK(x) do {++checks;if(!(x))throw std::runtime_error(#x);}while(0)
static Command take(Machine& m,Op op){auto c=m.take();CHECK(c && c->kind==op);CHECK(!m.take());return *c;}
static void done(Machine& m,Op op,const std::string& text="",std::uint64_t now=0){auto c=take(m,op);CHECK(m.complete({c,true,text,op==Op::Release},now));}
static void success(Machine& m,Policy p){
 done(m,Op::ReadWav);done(m,Op::Asr,"recognized");
 if(p==Policy::ReleaseBeforeTask)done(m,Op::Release);
 CHECK(m.state()==State::Handling);done(m,Op::Task,"reply");
 done(m,Op::Release);CHECK(m.state()==State::Speaking);
 done(m,Op::Tts);CHECK(m.state()!=State::Idle);done(m,Op::Release);
 CHECK(m.state()==State::Idle && m.outcome()==Outcome::Success);
}
int main(){try{
 for(auto p:{Policy::ReleaseBeforeTask,Policy::ReleaseBeforeTts}){
  Machine m({p,30,90,20});CHECK(m.start(0));CHECK(!m.start(0));success(m,p);
  CHECK(m.transcript()=="recognized");CHECK(m.start(0));CHECK(m.id()==2);success(m,p);
 }
 // Cancel while each worker stage is outstanding; no new work before release ACK.
 for(int stage=0;stage<7;++stage){
  Machine m;CHECK(m.start(0));
  Op sequence[]={Op::ReadWav,Op::Asr,Op::Release,Op::Task,Op::Release,Op::Tts,Op::Release};
  for(int i=0;i<stage;++i)done(m,sequence[i],"text");
  auto held=take(m,sequence[stage]);m.cancel();CHECK(m.state()==State::Cancelling);
  CHECK(!m.start(1));CHECK(!m.take());CHECK(m.complete({held,true,"late",false},1));
  CHECK(m.transcript()!="late");auto release=take(m,Op::Release);
  CHECK(m.complete({release,true,"",false},2));CHECK(!m.start(2));
  done(m,Op::Release,"",3);CHECK(m.state()==State::Idle);CHECK(m.start(3));
  CHECK(!m.complete({held,true,"stale",true},3));
 }
 {Machine m;CHECK(m.start(0));auto old=take(m,Op::ReadWav);CHECK(m.complete({old},0));
  auto c=take(m,Op::Asr);CHECK(!m.complete({old,true,"old",true},0));
  CHECK(m.complete({c,false},0));CHECK(m.state()==State::Cancelling);
  done(m,Op::Release);CHECK(m.state()==State::Error);CHECK(m.resetError());}
 // Exact timeout beats valid result; cleanup itself has no fictitious deadline ACK.
 {Machine m({Policy::ReleaseBeforeTask,10,25,20});CHECK(m.start(0));auto c=take(m,Op::ReadWav);
  CHECK(m.complete({c},10));CHECK(m.outcome()==Outcome::Timeout);m.tick(100000);
  CHECK(!m.start(100000));done(m,Op::Release,"",100000);CHECK(m.state()==State::Error);}
 {Machine m;CHECK(m.start(10));m.tick(9);done(m,Op::Release,"",11);
  CHECK(m.outcome()==Outcome::ClockError);CHECK(!m.resetError());}
 {Machine m;CHECK(m.start(0));done(m,Op::ReadWav);done(m,Op::Asr,"");done(m,Op::Release);
  CHECK(m.state()==State::Error);}
 {Machine m({Policy::ReleaseBeforeTask,10,100,3});CHECK(m.start(0));done(m,Op::ReadWav);
  done(m,Op::Asr,"large");done(m,Op::Release);CHECK(m.state()==State::Error);}
 {Machine m({},std::numeric_limits<std::uint64_t>::max());CHECK(m.start(0));
  success(m,Policy::ReleaseBeforeTask);CHECK(!m.start(0));}
 // Injection: load/read/task/TTS/release failures all roll back through release.
 for(int stage=0;stage<7;++stage){Machine m;CHECK(m.start(0));
  Op sequence[]={Op::ReadWav,Op::Asr,Op::Release,Op::Task,Op::Release,Op::Tts,Op::Release};
  for(int i=0;i<stage;++i)done(m,sequence[i],"text");
  auto c=take(m,sequence[stage]);CHECK(m.complete({c,false,"injected"},0));
  CHECK(m.state()==State::Cancelling);CHECK(!m.start(0));done(m,Op::Release);
  CHECK(m.state()==State::Error);CHECK(m.resetError());}
 {Machine m({Policy::ReleaseBeforeTask,10,15,20});CHECK(m.start(0));
  done(m,Op::ReadWav,"",9);done(m,Op::Asr,"text",15);
  CHECK(m.outcome()==Outcome::Timeout);done(m,Op::Release,"",15);}
 // Repeated deterministic stale-event/cancel/busy interleavings, fixed storage.
 for(unsigned i=0;i<1000;++i){Machine m;CHECK(m.start(0));auto c=take(m,Op::ReadWav);
  auto stale=c;stale.operation+=1;CHECK(!m.complete({stale},0));
  m.cancel();CHECK(!m.start(0));CHECK(m.complete({c},0));done(m,Op::Release);
  CHECK(m.outcome()==Outcome::Cancelled);}
 std::cout<<"mock_machine_checks="<<checks<<" failures=0\n";return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
