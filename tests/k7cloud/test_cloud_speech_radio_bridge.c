#include "cloud_speech_radio_bridge.h"

#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr, "CHECK failed at line %d: %s\n", __LINE__, #x); return 1; \
} } while (0)

struct fake { unsigned prompts; };

static int prompt(void *arg, enum cloud_speech_prompt which)
{
  struct fake *fake = arg;
  if (which != CLOUD_SPEECH_PROMPT_NETWORK_CONNECTED) return -1;
  fake->prompts++;
  return 0;
}

static int asr(void *arg, const char *token, const unsigned char *wav,
               size_t bytes, char *text, size_t capacity, size_t *written,
               bool (*cancelled)(void *), void *cancel_arg)
{
  (void)arg; (void)token; (void)wav; (void)bytes; (void)text;
  (void)capacity; (void)written; (void)cancelled; (void)cancel_arg;
  return -1;
}

static int tts(void *arg, const char *token, const char *text,
               const char *voice, unsigned char *wav, size_t capacity,
               size_t *written, bool (*cancelled)(void *), void *cancel_arg)
{
  (void)arg; (void)token; (void)text; (void)voice; (void)wav;
  (void)capacity; (void)written; (void)cancelled; (void)cancel_arg;
  return -1;
}

static int play(void *arg, const int16_t *pcm, size_t frames)
{
  (void)arg; (void)pcm; (void)frames; return -1;
}

int main(void)
{
  struct fake fake = {0};
  const struct cloud_speech_ops ops = {prompt, asr, tts, play};
  struct cloud_speech_orchestrator orchestrator;
  struct cloud_speech_radio_bridge bridge;
  unsigned char wav[48];
  int16_t pcm[1];
  struct cloud_speech_radio_snapshot snapshot = {0};

  CHECK(cloud_speech_init(&orchestrator, &ops, &fake, wav, sizeof(wav),
                          pcm, 1) == 0);
  CHECK(cloud_speech_radio_bridge_init(&bridge, &orchestrator) == 0);
  CHECK(cloud_speech_radio_bridge_apply(&bridge, &snapshot) == 0);
  CHECK(orchestrator.readiness == 0 && fake.prompts == 0);

  snapshot.generation = 1;
  snapshot.wifi_connected = true;
  snapshot.ipv4_ready = true;
  snapshot.ipv4[0] = 10; snapshot.ipv4[1] = 3;
  snapshot.ipv4[2] = 0; snapshot.ipv4[3] = 214;
  CHECK(cloud_speech_radio_bridge_apply(&bridge, &snapshot) == 0);
  CHECK(orchestrator.readiness == (CLOUD_SPEECH_WIFI_CONNECTED |
                                   CLOUD_SPEECH_IPV4_READY));
  CHECK(fake.prompts == 1 && !cloud_speech_is_ready(&orchestrator));
  cloud_speech_set_platform_readiness(&orchestrator, 0xffffffffu);
  CHECK(cloud_speech_is_ready(&orchestrator));
  CHECK(cloud_speech_radio_bridge_apply(&bridge, &snapshot) == 0);
  CHECK(fake.prompts == 1 && cloud_speech_is_ready(&orchestrator));

  memset(&snapshot, 0, sizeof(snapshot));
  snapshot.generation = 2;
  CHECK(cloud_speech_radio_bridge_apply(&bridge, &snapshot) == 0);
  CHECK(orchestrator.readiness == 0 && !cloud_speech_is_ready(&orchestrator));

  snapshot.wifi_connected = true;
  CHECK(cloud_speech_radio_bridge_apply(&bridge, &snapshot) ==
        CLOUD_SPEECH_EINVAL);
  CHECK(orchestrator.readiness == 0);

  memset(&snapshot, 0, sizeof(snapshot));
  snapshot.generation = 1;
  CHECK(cloud_speech_radio_bridge_apply(&bridge, &snapshot) ==
        CLOUD_SPEECH_EINVAL);

  snapshot.generation = 3;
  snapshot.wifi_connected = true;
  snapshot.ipv4_ready = true;
  snapshot.ipv4[0] = 169; snapshot.ipv4[1] = 254;
  CHECK(cloud_speech_radio_bridge_apply(&bridge, &snapshot) ==
        CLOUD_SPEECH_EINVAL);
  CHECK(orchestrator.readiness == 0);

  /* A reconnect can finish between polls, even with the same DHCP address.
   * New generations must not inherit the previous network's TLS/API gates. */
  snapshot.generation = 4;
  snapshot.ipv4[0] = 10; snapshot.ipv4[1] = 3;
  snapshot.ipv4[2] = 0; snapshot.ipv4[3] = 214;
  CHECK(cloud_speech_radio_bridge_apply(&bridge, &snapshot) == 0);
  cloud_speech_set_platform_readiness(&orchestrator, 0xffffffffu);
  CHECK(cloud_speech_is_ready(&orchestrator));
  snapshot.generation = 6;
  CHECK(cloud_speech_radio_bridge_apply(&bridge, &snapshot) == 0);
  CHECK(orchestrator.readiness == (CLOUD_SPEECH_WIFI_CONNECTED |
                                   CLOUD_SPEECH_IPV4_READY));
  CHECK(!cloud_speech_is_ready(&orchestrator));
  CHECK(fake.prompts == 3);

  puts("cloud speech radio bridge: 7 groups passed");
  return 0;
}
