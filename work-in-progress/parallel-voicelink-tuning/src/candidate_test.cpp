#define main probe_entry_not_used
#include "probe.cpp"
#undef main
#include "voicelink/audio.hpp"
int main(int argc,char**argv){
  if(argc!=3)return 2;
  Config cfg(argv[1],0);voicelink::SpeechSession s;
  if(!s.init(cfg.t,cfg.a))return 3;
  Owned<SherpaOnnxWave,SherpaOnnxFreeWave> w(SherpaOnnxReadWave(argv[2]),SherpaOnnxFreeWave);
  if(!w)return 4;
  std::vector<int16_t> pcm(w->num_samples);
  for(int i=0;i<w->num_samples;i++)pcm[i]=voicelink::floatToPcm16(w->samples[i]);
  std::atomic_bool stop{false};int failures=0,checks=0;std::string text;
  auto check=[&](bool pass,const char* name){++checks;if(!pass){++failures;std::cout<<"FAIL="<<name<<std::endl;}};
  auto feed=[&](int chunk){
    check(s.beginStream(),"begin");
    for(size_t i=0;i<pcm.size();i+=chunk)check(s.feed(pcm.data()+i,std::min<size_t>(chunk,pcm.size()-i),w->sample_rate,stop)==voicelink::AudioStatus::Ok,"feed");
  };
  for(int chunk:{160,512}){
    feed(chunk);
    check(s.finishWithTail(text,stop,w->sample_rate,300)==voicelink::AudioStatus::Ok,"tail finish");
    std::cout<<"chunk="<<chunk<<" text="<<text<<std::endl;
    check(text.size()>=std::string("星期三").size() && text.substr(text.size()-std::string("星期三").size())=="星期三","published reference suffix (not human accuracy)");
    check(s.finishWithTail(text,stop,w->sample_rate,300)==voicelink::AudioStatus::Invalid,"double EOF");check(text.empty(),"no stale text");
  }
  check(s.beginStream(),"empty begin");check(s.finishWithTail(text,stop,w->sample_rate,300)==voicelink::AudioStatus::Ok && text.empty(),"empty remains empty");
  feed(512);stop=true;check(s.finishWithTail(text,stop,w->sample_rate,300)==voicelink::AudioStatus::Cancelled,"cancel at EOF");
  stop=false;check(s.finish(text,stop)==voicelink::AudioStatus::Invalid,"cancel freed stream");
  check(s.beginStream(),"begin budget");bool hit=false;
  for(size_t i=0;i<pcm.size();i+=512){auto status=s.feed(pcm.data()+i,std::min<size_t>(512,pcm.size()-i),w->sample_rate,stop,0);if(status==voicelink::AudioStatus::DecodeLimit){hit=true;break;}}
  check(hit,"zero budget detects ready stream");check(s.finish(text,stop)==voicelink::AudioStatus::Invalid,"budget frees stream");
  check(s.beginStream(),"invalid begin");check(s.finishWithTail(text,stop,16000,2001)==voicelink::AudioStatus::Invalid,"tail bounded");
  check(s.finish(text,stop)==voicelink::AudioStatus::Invalid,"invalid frees stream");
  s.close();std::cout<<"checks="<<checks<<" failures="<<failures<<std::endl;return failures?1:0;
}
