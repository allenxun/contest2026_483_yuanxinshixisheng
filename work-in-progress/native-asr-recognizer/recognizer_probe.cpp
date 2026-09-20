#include "sherpa-onnx/c-api/c-api.h"
#include "test_assets.h"
#include <cstdio>
#include <cstring>
#include <ctime>
#include <exception>
#include <stdexcept>
#include <unistd.h>

namespace {
struct Handles {
 const SherpaOnnxOnlineRecognizer*recognizer=nullptr;
 const SherpaOnnxOnlineStream*stream=nullptr;
 const SherpaOnnxOnlineRecognizerResult*result=nullptr;
 ~Handles(){if(result)SherpaOnnxDestroyOnlineRecognizerResult(result);if(stream)SherpaOnnxDestroyOnlineStream(stream);if(recognizer)SherpaOnnxDestroyOnlineRecognizer(recognizer);}
};
double seconds(){timespec t{};if(clock_gettime(CLOCK_MONOTONIC,&t))throw std::runtime_error("clock");return t.tv_sec+t.tv_nsec/1e9;}
}
extern "C" int k7_asr_model_session_probe() {
 try {
  double start=seconds();Handles h;
  SherpaOnnxOnlineRecognizerConfig config{};
  config.feat_config.sample_rate=16000;config.feat_config.feature_dim=80;
  config.model_config.paraformer.encoder="k7ram:encoder";
  config.model_config.paraformer.decoder="k7ram:decoder";
  config.model_config.tokens_buf=reinterpret_cast<const char*>(test_tokens);
  config.model_config.tokens_buf_size=sizeof(test_tokens)-1;
  config.model_config.num_threads=1;config.model_config.provider="cpu";
  config.model_config.model_type="paraformer";config.decoding_method="greedy_search";
  std::puts("ASR_INFER BEGIN recognizer");std::fflush(stdout);
  h.recognizer=SherpaOnnxCreateOnlineRecognizer(&config);
  if(!h.recognizer)throw std::runtime_error("recognizer creation");
  h.stream=SherpaOnnxCreateOnlineStream(h.recognizer);
  if(!h.stream)throw std::runtime_error("stream creation");
  unsigned steps=0;
  auto decode=[&](){while(SherpaOnnxIsOnlineStreamReady(h.recognizer,h.stream)) {
   if(++steps>128||seconds()-start>180)throw std::runtime_error("decode budget");
   SherpaOnnxDecodeOnlineStream(h.recognizer,h.stream);
   std::printf("ASR_INFER chunk=%u elapsed=%.3f\n",steps,seconds()-start);std::fflush(stdout);usleep(1000);
  }};
  float samples[1600];
  for(unsigned offset=0;offset<test_frames;) {
   unsigned n=test_frames-offset;if(n>1600)n=1600;
   for(unsigned i=0;i<n;i++){unsigned j=2*(offset+i);int value=test_pcm[j]|(unsigned(test_pcm[j+1])<<8);if(value>=32768)value-=65536;samples[i]=float(value)/32768.0f;}
   SherpaOnnxOnlineStreamAcceptWaveform(h.stream,16000,samples,n);offset+=n;decode();
  }
  std::memset(samples,0,sizeof(samples));
  for(unsigned i=0;i<3;i++)SherpaOnnxOnlineStreamAcceptWaveform(h.stream,16000,samples,1600);
  SherpaOnnxOnlineStreamInputFinished(h.stream);decode();
  h.result=SherpaOnnxGetOnlineStreamResult(h.recognizer,h.stream);
  if(!h.result||!h.result->text||!h.result->text[0])throw std::runtime_error("empty recognition result");
  std::printf("ASR_INFER RESULT seconds=%.3f text=%s\n",seconds()-start,h.result->text);
  return 0;
 } catch(const std::exception&e){std::printf("ASR_INFER FAIL %s\n",e.what());return 1;}
 catch(...){std::puts("ASR_INFER FAIL unknown exception");return 1;}
}
