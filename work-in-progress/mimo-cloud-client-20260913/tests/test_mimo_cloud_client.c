#include "mimo_cloud_client.h"
#include "mimo_v25_profile.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct fake {
  const unsigned char *response;
  size_t response_len;
  size_t response_at;
  unsigned char written[16384];
  size_t written_len;
  uint64_t now;
  uint64_t step;
  bool cancel;
  char logs[512];
  size_t logs_len;
};

static uint64_t now_ms(void *arg) {
  struct fake *f = arg; uint64_t out = f->now; f->now += f->step; return out;
}
static bool cancelled(void *arg) { return ((struct fake *)arg)->cancel; }
static int connect_fn(void *arg, const char *host, uint16_t port,
                      uint64_t deadline, const struct vv_https_cancel *cancel,
                      struct vv_https_peer_security *security) {
  (void)arg; (void)host; (void)port; (void)deadline; (void)cancel;
  *security = (struct vv_https_peer_security){true, true, 0}; return 0;
}
static ssize_t write_fn(void *arg, const void *data, size_t len,
                        uint64_t deadline,
                        const struct vv_https_cancel *cancel) {
  struct fake *f = arg; (void)deadline; (void)cancel;
  size_t n = len > 11 ? 11 : len;
  if (n > sizeof(f->written) - f->written_len) return -EIO;
  memcpy(f->written + f->written_len, data, n); f->written_len += n;
  return (ssize_t)n;
}
static ssize_t read_fn(void *arg, void *data, size_t len, uint64_t deadline,
                       const struct vv_https_cancel *cancel) {
  struct fake *f = arg; (void)deadline; (void)cancel;
  if (f->response_at == f->response_len) return 0;
  size_t n = f->response_len - f->response_at;
  if (n > len) n = len;
  if (n > 7) n = 7;
  memcpy(data, f->response + f->response_at, n); f->response_at += n;
  return (ssize_t)n;
}
static void close_fn(void *arg) { (void)arg; }
static const struct vv_https_transport_ops ops = {
  connect_fn, write_fn, read_fn, close_fn
};
static void log_fn(void *arg, const char *event, int value) {
  struct fake *f = arg;
  int n = snprintf(f->logs + f->logs_len, sizeof(f->logs) - f->logs_len,
                   "%s=%d;", event, value);
  if (n > 0 && (size_t)n < sizeof(f->logs) - f->logs_len)
    f->logs_len += (size_t)n;
}

static struct mimo_cloud_protocol protocol = {
  .host = "api.invalid.test", .port = 443,
  .asr_path = "/profile/asr", .tts_path = "/profile/tts",
  .authorization_header = "Authorization",
  .authorization_scheme = "Bearer",
  .asr_model = "mimo-v2.5-asr", .tts_model = "mimo-v2.5-tts",
  .model_field = "model", .asr_audio_field = "audio",
  .asr_format_field = "format", .tts_text_field = "text",
  .tts_voice_field = "voice",
  .encode_asr = mimo_encode_flat_asr, .encode_tts = mimo_encode_flat_tts,
  .decode_asr = mimo_decode_flat_json_string,
  .decode_asr_arg = "transcript", .decode_tts = mimo_decode_wav
};

static struct mimo_cloud_client make_client(struct fake *f) {
  static struct vv_https_client https;
  https = (struct vv_https_client){
    .transport = &ops, .transport_ctx = f, .now_ms = now_ms, .now_arg = f,
    .log = log_fn, .log_arg = f, .limits = {2048, 2048, 4096, 4096, 1000}
  };
  return (struct mimo_cloud_client){
    .https = &https, .protocol = &protocol,
    .limits = {128, 4096, 512, 8192, 4096}, .log = log_fn, .log_arg = f
  };
}

static void response(struct fake *f, const unsigned char *body, size_t n,
                     int status) {
  static unsigned char wire[8192];
  int h = snprintf((char *)wire, sizeof(wire),
                   "HTTP/1.1 %d Status\r\nContent-Length: %zu\r\n\r\n",
                   status, n);
  memcpy(wire + h, body, n); f->response = wire; f->response_len = (size_t)h + n;
}

#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr, "%s:%d check failed: %s\n", __FILE__, __LINE__, #x); \
  return 1; } } while (0)

static int test_asr_success_and_redaction(void) {
  struct fake f = {0}; const char json[] = "{\"transcript\":\"你好联网\"}";
  response(&f, (const unsigned char *)json, sizeof(json) - 1, 200);
  struct mimo_cloud_client c = make_client(&f);
  const unsigned char pcm[] = {0, 1, 2, 3, 4};
  struct mimo_asr_request q = {"unit-test-secret", pcm, sizeof(pcm), "pcm_s16le"};
  struct vv_https_cancel cancel = {cancelled, &f};
  char text[64]; size_t n = 0;
  CHECK(mimo_cloud_transcribe(&c, &q, text, sizeof(text), &n, &cancel) == 0);
  CHECK(n == strlen("你好联网") && !strcmp(text, "你好联网"));
  f.written[f.written_len] = 0;
  CHECK(strstr((char *)f.written, "POST /profile/asr HTTP/1.1"));
  CHECK(strstr((char *)f.written, "\"audio\":\"AAECAwQ=\""));
  CHECK(strstr((char *)f.written, "Bearer unit-test-secret"));
  CHECK(!strstr(f.logs, "unit-test-secret"));
  CHECK(!strstr(f.logs, "你好联网"));
  CHECK(!strstr(f.logs, "AAECAwQ"));
  return 0;
}

static int test_tts_success(void) {
  struct fake f = {0}; unsigned char wav[44] = {0};
  memcpy(wav, "RIFF", 4); wav[4] = 36; memcpy(wav + 8, "WAVE", 4);
  response(&f, wav, sizeof(wav), 200);
  struct mimo_cloud_client c = make_client(&f);
  struct mimo_tts_request q = {"another-secret", "还没有联网，请联网。", "default"};
  struct vv_https_cancel cancel = {cancelled, &f};
  unsigned char out[64]; size_t n = 0;
  CHECK(mimo_cloud_synthesize(&c, &q, out, sizeof(out), &n, &cancel) == 0);
  CHECK(n == sizeof(wav) && !memcmp(out, wav, sizeof(wav)));
  f.written[f.written_len] = 0;
  CHECK(strstr((char *)f.written, "POST /profile/tts HTTP/1.1"));
  CHECK(strstr((char *)f.written, "mimo-v2.5-tts"));
  CHECK(!strstr(f.logs, "another-secret"));
  CHECK(!strstr(f.logs, "还没有联网"));
  return 0;
}

static int test_strict_responses(void) {
  struct fake f = {0}; struct mimo_cloud_client c = make_client(&f);
  const unsigned char pcm[] = {1};
  struct mimo_asr_request q = {"x", pcm, sizeof(pcm), "wav"};
  char out[16] = "UNCHANGED"; size_t n = 0;
  const char bad[] = "{\"transcript\":\"ok\",\"extra\":1}";
  response(&f, (const unsigned char *)bad, sizeof(bad) - 1, 200);
  CHECK(mimo_cloud_transcribe(&c, &q, out, sizeof(out), &n, NULL) ==
        MIMO_CLOUD_ERESPONSE);
  CHECK(n == 0 && !strcmp(out, "UNCHANGED"));
  memset(&f, 0, sizeof(f)); c = make_client(&f);
  response(&f, (const unsigned char *)"{}", 2, 503);
  CHECK(mimo_cloud_transcribe(&c, &q, out, sizeof(out), &n, NULL) ==
        MIMO_CLOUD_EHTTP);
  memset(&f, 0, sizeof(f)); c = make_client(&f);
  {
    const unsigned char invalid_utf8[] = {
      '{','"','t','r','a','n','s','c','r','i','p','t','"',':','"',0xc0,0x80,'"','}'
    };
    response(&f, invalid_utf8, sizeof(invalid_utf8), 200);
  }
  CHECK(mimo_cloud_transcribe(&c, &q, out, sizeof(out), &n, NULL) ==
        MIMO_CLOUD_ERESPONSE);
  return 0;
}

static int test_limits_and_validation(void) {
  struct fake f = {0}; struct mimo_cloud_client c = make_client(&f);
  const unsigned char pcm[] = {1, 2}; char out[8]; size_t n;
  struct mimo_asr_request q = {"bad\r\ntoken", pcm, sizeof(pcm), "wav"};
  CHECK(mimo_cloud_transcribe(&c, &q, out, sizeof(out), &n, NULL) ==
        MIMO_CLOUD_EINVAL);
  q.token = "ok"; c.limits.max_audio_input_bytes = 1;
  CHECK(mimo_cloud_transcribe(&c, &q, out, sizeof(out), &n, NULL) ==
        MIMO_CLOUD_EINVAL);
  c = make_client(&f); c.limits.max_request_body_bytes = 20;
  CHECK(mimo_cloud_transcribe(&c, &q, out, sizeof(out), &n, NULL) ==
        MIMO_CLOUD_ELIMIT);
  return 0;
}

static int test_cancel_and_timeout(void) {
  struct fake f = {.cancel = true}; struct mimo_cloud_client c = make_client(&f);
  const unsigned char pcm[] = {1}; char out[8]; size_t n;
  struct mimo_asr_request q = {"ok", pcm, sizeof(pcm), "wav"};
  struct vv_https_cancel cancel = {cancelled, &f};
  CHECK(mimo_cloud_transcribe(&c, &q, out, sizeof(out), &n, &cancel) ==
        VV_HTTPS_ECANCELLED);
  memset(&f, 0, sizeof(f)); f.step = 1001; c = make_client(&f);
  CHECK(mimo_cloud_transcribe(&c, &q, out, sizeof(out), &n, NULL) ==
        VV_HTTPS_ETIMEOUT);
  return 0;
}

static int test_output_not_partially_committed(void) {
  struct fake f = {0}; const char json[] = "{\"transcript\":\"too long\"}";
  response(&f, (const unsigned char *)json, sizeof(json) - 1, 200);
  struct mimo_cloud_client c = make_client(&f); const unsigned char pcm[] = {1};
  struct mimo_asr_request q = {"ok", pcm, sizeof(pcm), "wav"};
  char out[4] = "OLD"; size_t n = 123;
  CHECK(mimo_cloud_transcribe(&c, &q, out, sizeof(out), &n, NULL) ==
        MIMO_CLOUD_EOUTPUT);
  CHECK(n == 0); /* Caller can reject output solely by the returned length. */
  return 0;
}

static void put_le16(unsigned char *p, unsigned value) {
  p[0] = (unsigned char)value; p[1] = (unsigned char)(value >> 8);
}

static void put_le32(unsigned char *p, uint32_t value) {
  p[0] = (unsigned char)value; p[1] = (unsigned char)(value >> 8);
  p[2] = (unsigned char)(value >> 16); p[3] = (unsigned char)(value >> 24);
}

static void make_pcm_wav(unsigned char *wav, size_t bytes) {
  memset(wav, 0, bytes);
  memcpy(wav, "RIFF", 4); put_le32(wav + 4, (uint32_t)(bytes - 8));
  memcpy(wav + 8, "WAVEfmt ", 8); put_le32(wav + 16, 16);
  put_le16(wav + 20, 1); put_le16(wav + 22, 1);
  put_le32(wav + 24, 16000); put_le32(wav + 28, 32000);
  put_le16(wav + 32, 2); put_le16(wav + 34, 16);
  memcpy(wav + 36, "data", 4); put_le32(wav + 40, (uint32_t)(bytes - 44));
}

static size_t test_base64(const unsigned char *source, size_t length,
                          char *output) {
  static const char table[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  char *at = output;
  while (length >= 3) {
    *at++ = table[source[0] >> 2];
    *at++ = table[((source[0] & 3) << 4) | (source[1] >> 4)];
    *at++ = table[((source[1] & 15) << 2) | (source[2] >> 6)];
    *at++ = table[source[2] & 63]; source += 3; length -= 3;
  }
  if (length) {
    *at++ = table[source[0] >> 2];
    *at++ = table[((source[0] & 3) << 4) |
                  (length == 2 ? source[1] >> 4 : 0)];
    *at++ = length == 2 ? table[(source[1] & 15) << 2] : '=';
    *at++ = '=';
  }
  *at = 0;
  return (size_t)(at - output);
}

static int test_v25_request_profiles(void) {
  struct mimo_cloud_protocol p;
  unsigned char wav[46], body[2048]; size_t n = 999;
  struct mimo_asr_request asr = {"unused", wav, sizeof(wav), "wav"};
  struct mimo_tts_request tts = {"unused", "扫描到\"Lansee\"，请选择。", "冰糖"};
  make_pcm_wav(wav, sizeof(wav)); wav[44] = 1; wav[45] = 2;
  CHECK(mimo_v25_profile_init(&p, "token-plan-cn.xiaomimimo.com") == 0);
  CHECK(!strcmp(p.asr_path, "/v1/chat/completions"));
  CHECK(!strcmp(p.tts_path, "/v1/chat/completions"));
  CHECK(!strcmp(p.authorization_header, "Authorization"));
  CHECK(!strcmp(p.authorization_scheme, "Bearer"));
  CHECK(mimo_v25_encode_asr(&p, &asr, body, sizeof(body), &n) == 0);
  body[n] = 0;
  CHECK(strstr((char *)body, "\"model\":\"mimo-v2.5-asr\""));
  CHECK(strstr((char *)body, "\"role\":\"user\""));
  CHECK(strstr((char *)body, "\"type\":\"input_audio\""));
  CHECK(strstr((char *)body, "\"format\":\"wav\""));
  CHECK(strstr((char *)body, "\"asr_options\":{\"language\":\"zh\"}"));
  CHECK(strstr((char *)body, "\"stream\":false"));
  CHECK(!strstr((char *)body, "unused"));
  CHECK(mimo_v25_encode_tts(&p, &tts, body, sizeof(body), &n) == 0);
  body[n] = 0;
  CHECK(strstr((char *)body, "\"model\":\"mimo-v2.5-tts\""));
  CHECK(strstr((char *)body, "\"role\":\"assistant\""));
  CHECK(strstr((char *)body, "扫描到\\\"Lansee\\\"，请选择。"));
  CHECK(strstr((char *)body, "\"format\":\"wav\",\"voice\":\"冰糖\""));
  CHECK(!strstr((char *)body, "unused"));
  CHECK(mimo_v25_profile_init(&p, "https://bad.example/v1") ==
        MIMO_CLOUD_EINVAL);
  CHECK(mimo_v25_profile_init(&p, "bad.example\r\nInjected: yes") ==
        MIMO_CLOUD_EINVAL);
  return 0;
}

static int test_v25_unicode_asr_response(void) {
  const char raw[] = "{\"id\":\"x\",\"choices\":[{\"index\":0,\"message\":{"
    "\"role\":\"assistant\",\"content\":\"你好联网😀\"},"
    "\"finish_reason\":\"stop\"}],\"usage\":{\"seconds\":1.25}}";
  const char escaped[] = "{\"choices\":[{\"message\":{\"content\":"
    "\"\\u4f60\\u597d\\ud83d\\ude00\"}}]}";
  char output[64] = "old"; size_t n = 0;
  CHECK(mimo_v25_decode_asr(NULL, (const unsigned char *)raw,
        sizeof(raw) - 1, output, sizeof(output), &n) == 0);
  CHECK(n == strlen("你好联网😀") && !strcmp(output, "你好联网😀"));
  CHECK(mimo_v25_decode_asr(NULL, (const unsigned char *)escaped,
        sizeof(escaped) - 1, output, sizeof(output), &n) == 0);
  CHECK(n == strlen("你好😀") && !strcmp(output, "你好😀"));
  strcpy(output, "old"); n = 77;
  CHECK(mimo_v25_decode_asr(NULL, (const unsigned char *)raw,
        sizeof(raw) - 1, output, 4, &n) == MIMO_CLOUD_EOUTPUT);
  CHECK(n == 0 && !strcmp(output, "old"));
  return 0;
}

static int test_v25_tts_base64_wav_response(void) {
  unsigned char wav[48], output[64]; char encoded[80], json[512];
  size_t encoded_len, n = 0;
  make_pcm_wav(wav, sizeof(wav));
  wav[44] = 0x2f; wav[45] = 0xfb; wav[46] = 0xff; wav[47] = 0xee;
  encoded_len = test_base64(wav, sizeof(wav), encoded);
  CHECK(encoded_len && strchr(encoded, '/'));
  /* JSON may legally escape a slash inside the Base64 string. */
  {
    char escaped[96]; char *to = escaped;
    for (const char *from = encoded; *from; ++from) {
      if (*from == '/') *to++ = '\\';
      *to++ = *from;
    }
    *to = 0;
    snprintf(json, sizeof(json), "{\"choices\":[{\"message\":{"
             "\"content\":null,\"audio\":{\"id\":\"a\",\"data\":\"%s\"," 
             "\"expires_at\":null}}}]}", escaped);
  }
  memset(output, 0xa5, sizeof(output));
  CHECK(mimo_v25_decode_tts(NULL, (const unsigned char *)json, strlen(json),
        output, sizeof(output), &n) == 0);
  CHECK(n == sizeof(wav) && !memcmp(output, wav, sizeof(wav)));
  memset(output, 0xa5, sizeof(output)); n = 77;
  CHECK(mimo_v25_decode_tts(NULL, (const unsigned char *)json, strlen(json),
        output, 16, &n) == MIMO_CLOUD_EOUTPUT);
  CHECK(n == 0 && output[0] == 0xa5);
  return 0;
}

static int test_v25_strict_rejections(void) {
  const char *bad_asr[] = {
    "{\"choices\":[]}",
    "{\"choices\":[{\"message\":{\"content\":\"ok\",\"content\":\"x\"}}]}",
    "{\"choices\":[{\"message\":{\"content\":\"\\ud800\"}}]}",
    "{\"choices\":[{\"message\":{\"content\":\"ok\\u0000hidden\"}}]}",
    "{\"choices\":[{\"message\":{\"content\":\"ok\"}}]} trailing",
    "{\"choices\":[{\"message\":{\"content\":1}}]}"
  };
  const char *bad_tts[] = {
    "{\"choices\":[{\"message\":{\"audio\":{\"data\":\"A===\"}}}]}",
    "{\"choices\":[{\"message\":{\"audio\":{\"data\":\"AB==\"}}}]}",
    "{\"choices\":[{\"message\":{\"audio\":{\"data\":\"AAAA\"}}}]}",
    "{\"choices\":[{\"message\":{\"audio\":{\"data\":\"QUJDRA==\","
      "\"data\":\"QUJDRA==\"}}}]}"
  };
  unsigned char output[128]; size_t n;
  for (size_t i = 0; i < sizeof(bad_asr) / sizeof(bad_asr[0]); ++i) {
    memset(output, 0xa5, sizeof(output)); n = 77;
    CHECK(mimo_v25_decode_asr(NULL, (const unsigned char *)bad_asr[i],
          strlen(bad_asr[i]), output, sizeof(output), &n) ==
          MIMO_CLOUD_ERESPONSE);
    CHECK(n == 0 && output[0] == 0xa5);
  }
  for (size_t i = 0; i < sizeof(bad_tts) / sizeof(bad_tts[0]); ++i) {
    memset(output, 0xa5, sizeof(output)); n = 77;
    CHECK(mimo_v25_decode_tts(NULL, (const unsigned char *)bad_tts[i],
          strlen(bad_tts[i]), output, sizeof(output), &n) ==
          MIMO_CLOUD_ERESPONSE);
    CHECK(n == 0 && output[0] == 0xa5);
  }
  return 0;
}

static int test_v25_capacity_and_wav_boundaries(void) {
  struct mimo_cloud_protocol p; unsigned char body[512], wav[46];
  struct mimo_asr_request q = {"unused", wav, sizeof(wav), "wav"};
  size_t n = 91;
  make_pcm_wav(wav, sizeof(wav));
  CHECK(mimo_v25_profile_init(&p, "token-plan-cn.xiaomimimo.com") == 0);
  CHECK(mimo_v25_encode_asr(&p, &q, body, 10, &n) == MIMO_CLOUD_ELIMIT);
  CHECK(n == 0);
  q.audio_format = "pcm16";
  CHECK(mimo_v25_encode_asr(&p, &q, body, sizeof(body), &n) ==
        MIMO_CLOUD_EINVAL);
  q.audio_format = "wav"; wav[4] ^= 1;
  CHECK(mimo_v25_encode_asr(&p, &q, body, sizeof(body), &n) ==
        MIMO_CLOUD_EINVAL);
  {
    struct mimo_tts_request t = {"unused", "有效", "冰糖"};
    char invalid_utf8[] = {(char)0xc0, (char)0x80, 0};
    t.text = invalid_utf8;
    CHECK(mimo_v25_encode_tts(&p, &t, body, sizeof(body), &n) ==
          MIMO_CLOUD_EINVAL);
  }
  {
    const size_t at_limit = 7500000;
    unsigned char *large_wav = malloc(at_limit + 1);
    unsigned char *large_body = malloc(MIMO_V25_MAX_ASR_BASE64_BYTES + 512);
    CHECK(large_wav && large_body);
    make_pcm_wav(large_wav, at_limit);
    q.audio = large_wav; q.audio_bytes = at_limit; q.audio_format = "wav";
    CHECK(mimo_v25_encode_asr(&p, &q, large_body,
          MIMO_V25_MAX_ASR_BASE64_BYTES + 512, &n) == 0);
    CHECK(n > MIMO_V25_MAX_ASR_BASE64_BYTES);
    q.audio_bytes = at_limit + 1; q.audio_format = "mp3";
    CHECK(mimo_v25_encode_asr(&p, &q, large_body,
          MIMO_V25_MAX_ASR_BASE64_BYTES + 512, &n) == MIMO_CLOUD_ELIMIT);
    free(large_body); free(large_wav);
  }
  return 0;
}

static int test_v25_integrated_redaction(void) {
  struct fake f = {0}; struct mimo_cloud_protocol p;
  const char json[] = "{\"choices\":[{\"message\":{\"content\":\"你好联网\"}}]}";
  unsigned char wav[46]; char text[64]; size_t n = 0;
  make_pcm_wav(wav, sizeof(wav));
  response(&f, (const unsigned char *)json, sizeof(json) - 1, 200);
  CHECK(mimo_v25_profile_init(&p, "token-plan-cn.xiaomimimo.com") == 0);
  protocol = p;
  {
    struct mimo_cloud_client c = make_client(&f);
    struct mimo_asr_request q = {"profile-secret", wav, sizeof(wav), "wav"};
    CHECK(mimo_cloud_transcribe(&c, &q, text, sizeof(text), &n, NULL) == 0);
  }
  CHECK(!strcmp(text, "你好联网"));
  f.written[f.written_len] = 0;
  CHECK(strstr((char *)f.written, "POST /v1/chat/completions HTTP/1.1"));
  CHECK(strstr((char *)f.written, "Bearer profile-secret"));
  CHECK(strstr((char *)f.written, "\"type\":\"input_audio\""));
  CHECK(!strstr(f.logs, "profile-secret"));
  CHECK(!strstr(f.logs, "你好联网"));
  CHECK(!strstr(f.logs, "UklGR"));
  return 0;
}

int main(void) {
  int (*tests[])(void) = {test_asr_success_and_redaction, test_tts_success,
    test_strict_responses, test_limits_and_validation,
    test_cancel_and_timeout, test_output_not_partially_committed,
    test_v25_request_profiles, test_v25_unicode_asr_response,
    test_v25_tts_base64_wav_response, test_v25_strict_rejections,
    test_v25_capacity_and_wav_boundaries, test_v25_integrated_redaction};
  const char *names[] = {"asr_success_and_redaction", "tts_success",
    "strict_responses", "limits_and_validation", "cancel_and_timeout",
    "output_not_partially_committed", "v25_request_profiles",
    "v25_unicode_asr_response", "v25_tts_base64_wav_response",
    "v25_strict_rejections", "v25_capacity_and_wav_boundaries",
    "v25_integrated_redaction"};
  for (size_t i = 0; i < sizeof(tests) / sizeof(tests[0]); ++i) {
    if (tests[i]()) return 1;
    printf("PASS %s\n", names[i]);
  }
  puts("PASS all 12 groups"); return 0;
}
