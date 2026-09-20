#include "voicelink/audio.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <vector>
#include <cstring>
static void u32(std::ostream& s,uint32_t v){for(int i=0;i<4;i++)s.put(static_cast<char>(v>>(8*i)));}
static void u16(std::ostream& s,uint16_t v){s.put(static_cast<char>(v));s.put(static_cast<char>(v>>8));}
struct Sink:voicelink::PcmSink{
  int rate{};std::vector<uint8_t> data;
  bool begin(int r)noexcept override{rate=r;return r>0;}
  std::ptrdiff_t write(const uint8_t* p,std::size_t n)noexcept override{
    try{data.insert(data.end(),p,p+n);return static_cast<std::ptrdiff_t>(n);}catch(...){return -1;}
  }
  void end()noexcept override{}
  bool save(const char* path){std::ofstream f(path,std::ios::binary);f.write("RIFF",4);u32(f,36+data.size());f.write("WAVEfmt ",8);u32(f,16);u16(f,1);u16(f,1);u32(f,rate);u32(f,rate*2);u16(f,2);u16(f,16);f.write("data",4);u32(f,data.size());f.write(reinterpret_cast<char*>(data.data()),data.size());return bool(f);}
};
static uint32_t read32(std::istream& f){uint32_t v=0;for(int i=0;i<4;i++){int c=f.get();if(c<0)throw 1;v|=uint32_t(c)<<(8*i);}return v;}
static uint16_t read16(std::istream& f){uint16_t v=0;for(int i=0;i<2;i++){int c=f.get();if(c<0)throw 1;v|=uint16_t(c)<<(8*i);}return v;}
int main(int argc,char**argv){
  if(argc!=4)return 2;
  const std::string base=argv[1],t=base+"/vits-icefall-zh-aishell3/",a=base+"/sherpa-onnx-streaming-paraformer-bilingual-zh-en/";
  const std::string tm=t+"model.onnx",tt=t+"tokens.txt",tl=t+"lexicon.txt",tr=t+"rule.far",ae=a+"encoder.int8.onnx",ad=a+"decoder.int8.onnx",at=a+"tokens.txt";
  SherpaOnnxOfflineTtsConfig tc{};tc.model.vits.model=tm.c_str();tc.model.vits.tokens=tt.c_str();tc.model.vits.lexicon=tl.c_str();tc.rule_fars=tr.c_str();
  tc.model.vits.length_scale=1;tc.model.vits.noise_scale=.667f;tc.model.vits.noise_scale_w=.8f;tc.model.provider="cpu";tc.model.num_threads=1;tc.max_num_sentences=1;tc.silence_scale=1;
  SherpaOnnxOnlineRecognizerConfig ac{};ac.feat_config.sample_rate=16000;ac.feat_config.feature_dim=80;ac.model_config.paraformer.encoder=ae.c_str();ac.model_config.paraformer.decoder=ad.c_str();ac.model_config.tokens=at.c_str();ac.model_config.provider="cpu";ac.model_config.num_threads=1;ac.decoding_method="greedy_search";
  std::cout<<"runtime="<<SherpaOnnxGetVersionStr()<<" sha="<<SherpaOnnxGetGitSha1()<<"\n";
  auto start=std::chrono::steady_clock::now();voicelink::SpeechSession speech;
  if(!speech.init(tc,ac)){std::cerr<<"init failed\n";return 3;}
  auto elapsed=[&](){return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();};
  std::cout<<"both_models_loaded_seconds="<<elapsed()<<"\n";start=std::chrono::steady_clock::now();
  std::atomic_bool stop{false};Sink sink;
  auto status=speech.speak("你好，欢迎使用语音助手。",sink,stop);
  if(status!=voicelink::AudioStatus::Ok || !sink.save(argv[3]))return 4;
  std::cout<<"tts_seconds="<<elapsed()<<" sample_rate="<<sink.rate<<" pcm_samples="<<sink.data.size()/2<<"\n";
  std::vector<int16_t> pcm;uint32_t rate=0;bool format=false;
  try{
    std::ifstream f(argv[2],std::ios::binary);char magic[4];f.read(magic,4);if(std::memcmp(magic,"RIFF",4))return 5;(void)read32(f);f.read(magic,4);if(std::memcmp(magic,"WAVE",4))return 5;
    while(f.read(magic,4)){
      auto size=read32(f);auto pos=f.tellg();
      if(!std::memcmp(magic,"fmt ",4)){if(size<16 || read16(f)!=1 || read16(f)!=1)return 5;rate=read32(f);(void)read32(f);(void)read16(f);if(read16(f)!=16)return 5;format=true;}
      if(!std::memcmp(magic,"data",4)){if(!format || size%2)return 5;for(uint32_t i=0;i<size/2;i++)pcm.push_back(static_cast<int16_t>(read16(f)));break;}
      f.seekg(pos+static_cast<std::streamoff>(size+(size&1)));
    }
  }catch(...){return 5;}
  if(pcm.empty() || !rate)return 5;
  start=std::chrono::steady_clock::now();if(!speech.beginStream())return 6;
  for(std::size_t i=0;i<pcm.size();i+=512){auto n=std::min<std::size_t>(512,pcm.size()-i);if(speech.feed(pcm.data()+i,n,rate,stop)!=voicelink::AudioStatus::Ok)return 7;}
  std::string text;if(speech.finish(text,stop)!=voicelink::AudioStatus::Ok)return 8;
  std::cout<<"asr_seconds="<<elapsed()<<" input_rate="<<rate<<" input_samples="<<pcm.size()<<" tail_padding_samples=0\ntext="<<text<<"\n";
  speech.close();return text.empty()?9:0;
}
