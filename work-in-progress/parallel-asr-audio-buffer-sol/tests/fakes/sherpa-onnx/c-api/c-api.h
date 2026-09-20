#ifndef FAKE_SHERPA_ONNX_C_API_H
#define FAKE_SHERPA_ONNX_C_API_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SherpaOnnxOnlineRecognizer SherpaOnnxOnlineRecognizer;
typedef struct SherpaOnnxOnlineStream SherpaOnnxOnlineStream;
typedef struct SherpaOnnxOnlineRecognizerResult {
  const char *text;
} SherpaOnnxOnlineRecognizerResult;

typedef struct { int sample_rate; int feature_dim; } SherpaOnnxFeatureConfig;
typedef struct { const char *encoder; const char *decoder; } SherpaOnnxParaformerModelConfig;
typedef struct {
  SherpaOnnxParaformerModelConfig paraformer;
  const char *tokens_buf;
  size_t tokens_buf_size;
  int num_threads;
  const char *provider;
  const char *model_type;
} SherpaOnnxOnlineModelConfig;
typedef struct {
  SherpaOnnxFeatureConfig feat_config;
  SherpaOnnxOnlineModelConfig model_config;
  const char *decoding_method;
} SherpaOnnxOnlineRecognizerConfig;

const SherpaOnnxOnlineRecognizer *SherpaOnnxCreateOnlineRecognizer(const SherpaOnnxOnlineRecognizerConfig *);
void SherpaOnnxDestroyOnlineRecognizer(const SherpaOnnxOnlineRecognizer *);
const SherpaOnnxOnlineStream *SherpaOnnxCreateOnlineStream(const SherpaOnnxOnlineRecognizer *);
void SherpaOnnxDestroyOnlineStream(const SherpaOnnxOnlineStream *);
int SherpaOnnxIsOnlineStreamReady(const SherpaOnnxOnlineRecognizer *, const SherpaOnnxOnlineStream *);
void SherpaOnnxDecodeOnlineStream(const SherpaOnnxOnlineRecognizer *, const SherpaOnnxOnlineStream *);
void SherpaOnnxOnlineStreamAcceptWaveform(const SherpaOnnxOnlineStream *, int, const float *, int);
void SherpaOnnxOnlineStreamInputFinished(const SherpaOnnxOnlineStream *);
const SherpaOnnxOnlineRecognizerResult *SherpaOnnxGetOnlineStreamResult(const SherpaOnnxOnlineRecognizer *, const SherpaOnnxOnlineStream *);
void SherpaOnnxDestroyOnlineRecognizerResult(const SherpaOnnxOnlineRecognizerResult *);

#ifdef __cplusplus
}
#endif
#endif
