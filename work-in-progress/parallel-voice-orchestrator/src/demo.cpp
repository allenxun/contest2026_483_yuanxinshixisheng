#include "orchestrator.hpp"
#include "voicelink/audio.hpp"
#include "mock_wifi_task.hpp"
#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>
using namespace voice;
using namespace voicelink;
using Clock=std::chrono::steady_clock;
static auto origin=Clock::now();
static std::uint64_t now(){return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-origin).count();}
static void mark(const char* s){std::cout<<"mark="<<s<<" ms="<<now()<<std::endl;}
struct Models {
 std::string tm,tt,lex,far,enc,dec,tok;
 SherpaOnnxOfflineTtsConfig t{};SherpaOnnxOnlineRecognizerConfig a{};
 explicit Models(const std::string& base){
  auto td=base+"/vits-icefall-zh-aishell3/",ad=base+"/sherpa-onnx-streaming-paraformer-bilingual-zh-en/";
  tm=td+"model.onnx";tt=td+"tokens.txt";lex=td+"lexicon.txt";far=td+"rule.far";
  enc=ad+"encoder.int8.onnx";dec=ad+"decoder.int8.onnx";tok=ad+"tokens.txt";
  t.model.vits.model=tm.c_str();t.model.vits.tokens=tt.c_str();t.model.vits.lexicon=lex.c_str();t.rule_fars=far.c_str();
  t.model.vits.length_scale=1;t.model.vits.noise_scale=.667f;t.model.vits.noise_scale_w=.8f;
  t.model.provider="cpu";t.model.num_threads=1;t.max_num_sentences=1;t.silence_scale=1;
  a.feat_config.sample_rate=16000;a.feat_config.feature_dim=80;
  a.model_config.paraformer.encoder=enc.c_str();a.model_config.paraformer.decoder=dec.c_str();
  a.model_config.tokens=tok.c_str();a.model_config.provider="cpu";a.model_config.num_threads=1;
  a.decoding_method="greedy_search";a.enable_endpoint=0;
 }
 Models(const Models&)=delete;Models& operator=(const Models&)=delete;
};
class ExampleTask:public TaskPort {
 std::string handle(std::uint64_t,const std::string& text,const std::atomic_bool& stop) override {
  if(stop.load() || text.empty())throw std::runtime_error("task cancelled/empty");
  return "你好，已收到语音。"; // fixed response; no intent comprehension or Agent
 }
 void close()noexcept override{}
};
class WavSink:public PcmSink {
 public:
 bool begin(int r)noexcept override {rate=r;data.clear();return r==8000;}
 std::ptrdiff_t write(const std::uint8_t* p,std::size_t n)noexcept override{
  if(n>2000000-data.size())return -1;
  try{data.insert(data.end(),p,p+n);return static_cast<std::ptrdiff_t>(n);}catch(...){return -1;}
 }
 void end()noexcept override{}
 void save(const std::string& path){
  if(data.empty() || data.size()%2 || std::filesystem::exists(path))throw std::runtime_error("invalid/existing output");
  std::ofstream f(path,std::ios::binary);if(!f)throw std::runtime_error("output open");
  auto u16=[&](unsigned v){f.put(static_cast<char>(v));f.put(static_cast<char>(v>>8));};
  auto u32=[&](unsigned v){u16(v&65535);u16(v>>16);};
  f.write("RIFF",4);u32(36+static_cast<unsigned>(data.size()));f.write("WAVEfmt ",8);u32(16);
  u16(1);u16(1);u32(rate);u32(rate*2);u16(2);u16(16);f.write("data",4);
  u32(static_cast<unsigned>(data.size()));f.write(reinterpret_cast<const char*>(data.data()),data.size());
  f.close();if(!f)throw std::runtime_error("output write");
 }
 int rate=0;std::vector<std::uint8_t> data;
};
class Worker {
 public:
 Worker(std::string base,std::string wav,std::string out,bool wifi):models(base),wavPath(std::move(wav)),outPath(std::move(out)),
 task(wifi?static_cast<TaskPort*>(new MockWifiTask):static_cast<TaskPort*>(new ExampleTask)){}
 ~Worker(){stop=true;if(future.valid())future.wait();close();}
 void launch(Command cmd,const std::string& text){
  if(future.valid())throw std::runtime_error("worker capacity exceeded");
  future=std::async(std::launch::async,[this,cmd,text]{return execute(cmd,text);});
 }
 bool ready(){return future.valid() && future.wait_for(std::chrono::milliseconds(0))==std::future_status::ready;}
 Event get(){return future.get();}
 std::atomic_bool stop{false};
 private:
 void close()noexcept{speech.close();wave.reset();task->close();}
 Event execute(Command cmd,const std::string& text){
  Event e{cmd,true,"",false};
  try{
   if(cmd.kind==Op::Release){close();mark("release_complete");e.released=true;return e;}
   if(stop.load())throw std::runtime_error("cancelled");
   switch(cmd.kind){
    case Op::ReadWav:{
     // Same native narrow-path convention as the pinned C API on Windows.
     std::ifstream sizeProbe(wavPath,std::ios::binary|std::ios::ate);
     if(!sizeProbe || sizeProbe.tellg()<0 || sizeProbe.tellg()>2000000)throw std::runtime_error("WAV missing/capacity");
     wave.reset(SherpaOnnxReadWave(wavPath.c_str()));
     if(!wave || wave->sample_rate!=16000 || wave->num_samples<=0 || wave->num_samples>960000)
      throw std::runtime_error("requires bounded mono 16k WAV");
     mark("wav_loaded");break;}
    case Op::Asr:{
     mark("asr_load_begin");if(!speech.initAsr(models.a))throw std::runtime_error("asr load");mark("asr_loaded");
     if(!speech.beginStream())throw std::runtime_error("stream create");
     std::array<std::int16_t,512> chunk{};
     for(int pos=0;pos<wave->num_samples;pos+=512){
      int n=std::min(512,wave->num_samples-pos);
      for(int i=0;i<n;++i)chunk[i]=floatToPcm16(wave->samples[pos+i]);
      if(speech.feed(chunk.data(),n,16000,stop)!=AudioStatus::Ok)throw std::runtime_error("feed/cancel");
     }
     if(speech.finishWithTail(e.text,stop,16000,300)!=AudioStatus::Ok)throw std::runtime_error("finish/cancel");
     wave.reset();mark("asr_finished");break;}
    case Op::Task:e.text=task->handle(cmd.transaction,text,stop);mark("example_task_finished");break;
    case Op::Tts:{
     mark("tts_load_begin");if(!speech.initTts(models.t))throw std::runtime_error("tts load");mark("tts_loaded");
     WavSink sink;if(speech.speak(text.c_str(),sink,stop)!=AudioStatus::Ok)throw std::runtime_error("speak/cancel");
     // Keep bytes private until coordinator accepts result; no late cancelled output commit.
     audio=std::move(sink);mark("tts_finished");break;}
    case Op::Release:break;
   }
  }catch(const std::exception& ex){e.ok=false;e.text=ex.what();}
  catch(...){e.ok=false;e.text="unknown worker exception";}
  return e;
 }
 public:
 void commit(){audio.save(outPath);}
 private:
 Models models;std::string wavPath,outPath;SpeechSession speech;
 std::unique_ptr<TaskPort> task;
 std::unique_ptr<const SherpaOnnxWave,decltype(&SherpaOnnxFreeWave)> wave{nullptr,SherpaOnnxFreeWave};
 WavSink audio;std::future<Event> future;
};
int main(int argc,char** argv){
 if(argc!=7)return 2;
 try{
  std::cout<<"sherpa="<<SherpaOnnxGetVersionStr()<<" sha="<<SherpaOnnxGetGitSha1()<<std::endl;
  if(std::string(SherpaOnnxGetVersionStr())!="1.12.14")throw std::runtime_error("version mismatch");
  const auto cancelAt=std::stoull(argv[5]);
  Config cfg;cfg.policy=std::string(argv[4])=="hold"?Policy::ReleaseBeforeTts:Policy::ReleaseBeforeTask;
  Machine machine(cfg);Worker worker(argv[1],argv[2],argv[3],std::string(argv[6])=="wifi-mock");
  machine.start(now());
  while(machine.state()!=State::Idle && machine.state()!=State::Error){
   machine.tick(now());if(cancelAt && now()>=cancelAt)machine.cancel();
   if(machine.stopRequested())worker.stop=true;
   if(worker.ready()){
    auto e=worker.get();std::cout<<"event tx="<<e.command.transaction<<" op="<<e.command.operation
     <<" kind="<<static_cast<int>(e.command.kind)<<" ok="<<e.ok<<" released="<<e.released<<std::endl;
    if(!e.ok)std::cout<<"worker_error="<<e.text<<std::endl;
    machine.complete(e,now());
   }
   if(auto c=machine.take())worker.launch(*c,c->kind==Op::Task?machine.transcript():machine.reply());
   std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
  std::cout<<"transcript="<<machine.transcript()<<"\nreply="<<machine.reply()
   <<"\noutcome="<<static_cast<int>(machine.outcome())<<std::endl;
  if(machine.outcome()==Outcome::Success){worker.commit();return 0;}
  return machine.outcome()==Outcome::Cancelled?20:3;
 }catch(const std::exception& ex){std::cerr<<ex.what()<<std::endl;return 3;}
}
