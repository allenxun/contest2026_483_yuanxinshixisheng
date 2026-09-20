#include <sherpa-onnx/c-api/c-api.h>
#include <algorithm>
#include <chrono>
#include <iostream>
#include <iomanip>
#include <memory>
#include <string>
#include <thread>
#include <vector>
using Clock=std::chrono::steady_clock;
static Clock::time_point origin=Clock::now();
static double seconds(){return std::chrono::duration<double>(Clock::now()-origin).count();}
static void mark(const std::string& name){std::cout<<"mark="<<name<<" time="<<seconds()<<std::endl;}
template<class T, void (*D)(const T*)> using Owned=std::unique_ptr<const T,decltype(D)>;
using Asr=Owned<SherpaOnnxOnlineRecognizer,SherpaOnnxDestroyOnlineRecognizer>;
using Tts=Owned<SherpaOnnxOfflineTts,SherpaOnnxDestroyOfflineTts>;
using Stream=Owned<SherpaOnnxOnlineStream,SherpaOnnxDestroyOnlineStream>;
using Result=Owned<SherpaOnnxOnlineRecognizerResult,SherpaOnnxDestroyOnlineRecognizerResult>;
struct Config {
  std::string tmodel,ttokens,lexicon,far,encoder,decoder,tokens;
  SherpaOnnxOfflineTtsConfig t{};SherpaOnnxOnlineRecognizerConfig a{};
  Config(const std::string& base,int endpoint){
    const auto td=base+"/vits-icefall-zh-aishell3/",ad=base+"/sherpa-onnx-streaming-paraformer-bilingual-zh-en/";
    tmodel=td+"model.onnx";ttokens=td+"tokens.txt";lexicon=td+"lexicon.txt";far=td+"rule.far";
    encoder=ad+"encoder.int8.onnx";decoder=ad+"decoder.int8.onnx";tokens=ad+"tokens.txt";
    t.model.vits.model=tmodel.c_str();t.model.vits.tokens=ttokens.c_str();t.model.vits.lexicon=lexicon.c_str();t.rule_fars=far.c_str();
    t.model.vits.length_scale=1;t.model.vits.noise_scale=.667f;t.model.vits.noise_scale_w=.8f;t.model.provider="cpu";t.model.num_threads=1;t.max_num_sentences=1;t.silence_scale=1;
    a.feat_config.sample_rate=16000;a.feat_config.feature_dim=80;a.model_config.paraformer.encoder=encoder.c_str();a.model_config.paraformer.decoder=decoder.c_str();a.model_config.tokens=tokens.c_str();a.model_config.provider="cpu";a.model_config.num_threads=1;a.decoding_method="greedy_search";
    a.enable_endpoint=endpoint;a.rule1_min_trailing_silence=2.4f;a.rule2_min_trailing_silence=1.2f;a.rule3_min_utterance_length=20;
  }
};
static std::string text(const SherpaOnnxOnlineRecognizer* r,const SherpaOnnxOnlineStream* s){
  Result result(SherpaOnnxGetOnlineStreamResult(r,s),SherpaOnnxDestroyOnlineRecognizerResult);
  if(!result || !result->text)throw std::runtime_error("null result");
  return result->text;
}
static void tts(const SherpaOnnxOfflineTts* t){
  mark("tts_begin");Owned<SherpaOnnxGeneratedAudio,SherpaOnnxDestroyOfflineTtsGeneratedAudio> audio(
    SherpaOnnxOfflineTtsGenerate(t,"你好，欢迎使用语音助手。",0,1),SherpaOnnxDestroyOfflineTtsGeneratedAudio);
  if(!audio || audio->n<=0)throw std::runtime_error("tts failure");
  mark("tts_first_complete_audio");std::cout<<"tts_frames="<<audio->n<<" rate="<<audio->sample_rate<<std::endl;
}
static int asr(const SherpaOnnxOnlineRecognizer* r,const char* wav,int chunk,int tail,int lead,int budget,const std::string& action){
  Owned<SherpaOnnxWave,SherpaOnnxFreeWave> w(SherpaOnnxReadWave(wav),SherpaOnnxFreeWave);
  if(!w)throw std::runtime_error("wav failure");
  Stream s(SherpaOnnxCreateOnlineStream(r),SherpaOnnxDestroyOnlineStream);
  if(!s)throw std::runtime_error("stream failure");
  int total_decodes=0,max_drain=0,endpoint_hits=0;bool first=false;
  auto drain=[&](){
    int count=0;
    while(SherpaOnnxIsOnlineStreamReady(r,s.get())){
      if(count>=budget){std::cout<<"failure=decode_budget total_decodes="<<total_decodes<<std::endl;return false;}
      SherpaOnnxDecodeOnlineStream(r,s.get());++count;++total_decodes;
    }
    max_drain=std::max(max_drain,count);
    if(count && !first && !text(r,s.get()).empty()){first=true;mark("asr_first_nonempty");}
    if(SherpaOnnxOnlineStreamIsEndpoint(r,s.get()))++endpoint_hits;
    return true;
  };
  auto feed=[&](const float* p,int n){for(int i=0;i<n;i+=chunk){int count=std::min(chunk,n-i);SherpaOnnxOnlineStreamAcceptWaveform(s.get(),w->sample_rate,p+i,count);if(!drain())return false;}return true;};
  mark("asr_begin");
  std::vector<float> leading(w->sample_rate*lead/1000,0),trailing(w->sample_rate*tail/1000,0);
  if(!feed(leading.data(),static_cast<int>(leading.size())))return 21;
  const int n=action=="empty"?0:(action=="cancel"?w->num_samples/2:w->num_samples);
  if(!feed(w->samples,n))return 21;
  std::cout<<"before_tail="<<std::quoted(text(r,s.get()))<<std::endl;
  if(action=="cancel"){s.reset();mark("cancelled_without_result_commit");return 20;}
  if(!feed(trailing.data(),static_cast<int>(trailing.size())))return 21;
  std::cout<<"before_finished="<<std::quoted(text(r,s.get()))<<std::endl;
  SherpaOnnxOnlineStreamInputFinished(s.get());
  if(!drain())return 21;
  mark("asr_final");std::cout<<"text="<<std::quoted(text(r,s.get()))<<"\ndecodes="<<total_decodes<<" max_drain="<<max_drain<<" endpoint_hits="<<endpoint_hits<<std::endl;
  return 0;
}
int main(int argc,char**argv){
  if(argc!=10)return 2;
  std::string mode=argv[1],action=argv[9];int chunk=std::stoi(argv[4]),tail=std::stoi(argv[5]),lead=std::stoi(argv[6]),endpoint=std::stoi(argv[7]),budget=std::stoi(argv[8]);
  if(chunk<1||tail<0||tail>2000||lead<0||lead>1000||budget<0||budget>1024)return 2;
  try{
    std::cout<<"version="<<SherpaOnnxGetVersionStr()<<" sha="<<SherpaOnnxGetGitSha1()<<std::endl;
    Config cfg(argv[2],endpoint);Asr a(nullptr,SherpaOnnxDestroyOnlineRecognizer);Tts t(nullptr,SherpaOnnxDestroyOfflineTts);
    auto loadA=[&](){mark("asr_load_begin");a.reset(SherpaOnnxCreateOnlineRecognizer(&cfg.a));if(!a)throw std::runtime_error("asr load");mark("asr_loaded");};
    auto loadT=[&](){mark("tts_load_begin");t.reset(SherpaOnnxCreateOfflineTts(&cfg.t));if(!t)throw std::runtime_error("tts load");mark("tts_loaded");};
    int rc=0;mark("baseline");
    if(mode=="tts"){loadT();tts(t.get());}
    else if(mode=="asr"){loadA();rc=asr(a.get(),argv[3],chunk,tail,lead,budget,action);}
    else if(mode=="both"){loadT();loadA();tts(t.get());rc=asr(a.get(),argv[3],chunk,tail,lead,budget,action);}
    else if(mode=="sequential"){
      loadA();rc=asr(a.get(),argv[3],chunk,tail,lead,budget,action);a.reset();mark("asr_released");std::this_thread::sleep_for(std::chrono::milliseconds(250));
      loadT();tts(t.get());
    }else return 2;
    a.reset();t.reset();mark("all_released");std::this_thread::sleep_for(std::chrono::milliseconds(250));return rc;
  }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 3;}
}
