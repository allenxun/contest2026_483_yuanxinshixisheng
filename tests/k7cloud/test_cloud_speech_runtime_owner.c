#include "cloud_speech_runtime_owner.h"

#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr, "line %d: %s\n", __LINE__, #x); return 1; \
} } while (0)

struct fake {
  struct cloud_speech_radio_snapshot snapshot;
  struct cloud_speech_runtime_owner *owner;
  unsigned reads, prompts, cloud_calls;
  int read_error, prompt_error, nested_result;
  bool reenter;
};

static int read_radio(void *arg, struct cloud_speech_radio_snapshot *snapshot)
{
  struct fake *f = arg;
  ++f->reads;
  if (f->reenter) f->nested_result = cloud_speech_runtime_owner_cancel(f->owner);
  *snapshot = f->snapshot;
  return f->read_error;
}
static int prompt(void *arg, enum cloud_speech_prompt which)
{
  struct fake *f = arg;
  ++f->prompts;
  return which == CLOUD_SPEECH_PROMPT_NETWORK_CONNECTED ? f->prompt_error : -1;
}
static int asr(void *arg, const char *token, const unsigned char *wav,
               size_t bytes, char *text, size_t capacity, size_t *written,
               bool (*cancelled)(void *), void *cancel_arg)
{
  struct fake *f = arg;
  (void)token; (void)wav; (void)bytes; (void)text; (void)capacity;
  (void)written; (void)cancelled; (void)cancel_arg;
  ++f->cloud_calls;
  return -1;
}
static int tts(void *arg, const char *token, const char *text,
               const char *voice, unsigned char *wav, size_t capacity,
               size_t *written, bool (*cancelled)(void *), void *cancel_arg)
{
  struct fake *f = arg;
  (void)token; (void)text; (void)voice; (void)wav; (void)capacity;
  (void)written; (void)cancelled; (void)cancel_arg;
  ++f->cloud_calls;
  return -1;
}
static int play(void *arg, const int16_t *pcm, size_t frames)
{
  (void)arg; (void)pcm; (void)frames;
  return -1;
}

int main(void)
{
  struct cloud_speech_runtime_owner owner = {0};
  struct fake fake = {0};
  const struct cloud_speech_ops ops = {prompt, asr, tts, play};
  unsigned char wav[48];
  int16_t pcm[1];
  const uint32_t network = CLOUD_SPEECH_WIFI_CONNECTED | CLOUD_SPEECH_IPV4_READY;
  fake.owner = &owner;

  CHECK(cloud_speech_runtime_owner_start(NULL) == CLOUD_SPEECH_EINVAL);
  CHECK(cloud_speech_runtime_owner_start(&owner) == CLOUD_SPEECH_EINVAL);
  CHECK(cloud_speech_runtime_owner_init(&owner, &ops, &fake, wav, sizeof(wav),
    pcm, 1, NULL, &fake) == CLOUD_SPEECH_EINVAL);
  CHECK(!owner.initialized);
  CHECK(cloud_speech_runtime_owner_init(&owner, &ops, &fake, wav, sizeof(wav),
    pcm, 1, read_radio, &fake) == 0);
  CHECK(cloud_speech_runtime_owner_poll(&owner) == CLOUD_SPEECH_ENOTREADY);
  CHECK(fake.reads == 0);

  /* Failed initial read cannot leave platform gates set; retry is explicit. */
  fake.read_error = -55;
  CHECK(cloud_speech_runtime_owner_start(&owner) == -55);
  CHECK(owner.running && owner.speech.readiness == 0);
  CHECK(!cloud_speech_runtime_owner_ready(&owner));
  CHECK(cloud_speech_runtime_owner_start(&owner) == CLOUD_SPEECH_EBUSY);
  fake.read_error = 0;
  CHECK(cloud_speech_runtime_owner_poll(&owner) == 0);
  CHECK(fake.prompts == 0);

  /* Healthy polls play once and open exactly two gates. */
  fake.snapshot = (struct cloud_speech_radio_snapshot){1, true, true, {10,3,0,214}};
  CHECK(cloud_speech_runtime_owner_poll(&owner) == 0);
  CHECK(cloud_speech_runtime_owner_poll(&owner) == 0);
  CHECK(fake.prompts == 1 && owner.speech.readiness == network);
  CHECK(!cloud_speech_runtime_owner_ready(&owner));
  cloud_speech_set_platform_readiness(&owner.speech, CLOUD_SPEECH_REQUIRED_BITS);
  CHECK(cloud_speech_runtime_owner_ready(&owner));

  /* Reconnect entirely between polls invalidates all six independent gates. */
  fake.snapshot.generation = 3;
  CHECK(cloud_speech_runtime_owner_poll(&owner) == 0);
  CHECK(fake.prompts == 2 && owner.speech.readiness == network);
  cloud_speech_set_platform_readiness(&owner.speech, CLOUD_SPEECH_REQUIRED_BITS);
  fake.snapshot = (struct cloud_speech_radio_snapshot){4, false, false, {0}};
  CHECK(cloud_speech_runtime_owner_poll(&owner) == 0);
  CHECK(owner.speech.readiness == 0);

  /* Cancel preserves generation protection; restart cannot accept stale state. */
  CHECK(cloud_speech_runtime_owner_cancel(&owner) == 0);
  CHECK(cloud_speech_runtime_owner_cancel(&owner) == 0);
  CHECK(!owner.running && owner.speech.readiness == 0);
  CHECK(cloud_speech_runtime_owner_poll(&owner) == CLOUD_SPEECH_ENOTREADY);
  fake.snapshot.generation = 2;
  CHECK(cloud_speech_runtime_owner_start(&owner) == CLOUD_SPEECH_EINVAL);
  CHECK(owner.speech.readiness == 0);
  fake.snapshot = (struct cloud_speech_radio_snapshot){5, true, true, {10,3,0,214}};

  /* Missing/failed fixed audio blocks readiness, and can recover on retry. */
  fake.prompt_error = -1;
  CHECK(cloud_speech_runtime_owner_poll(&owner) == CLOUD_SPEECH_EPLAY);
  CHECK(owner.speech.readiness == 0);
  fake.prompt_error = 0;
  CHECK(cloud_speech_runtime_owner_poll(&owner) == 0);
  CHECK(owner.speech.readiness == network);
  cloud_speech_set_platform_readiness(&owner.speech, CLOUD_SPEECH_REQUIRED_BITS);
  fake.read_error = -56;
  CHECK(cloud_speech_runtime_owner_poll(&owner) == -56);
  CHECK(owner.speech.readiness == 0);
  fake.read_error = 0;
  CHECK(cloud_speech_runtime_owner_poll(&owner) == 0);
  CHECK(owner.speech.readiness == network);

  /* Reject synchronous callback re-entry and active speech, without races. */
  fake.reenter = true;
  CHECK(cloud_speech_runtime_owner_poll(&owner) == 0);
  CHECK(fake.nested_result == CLOUD_SPEECH_EBUSY && owner.running);
  fake.reenter = false;
  owner.speech.busy = true;
  CHECK(cloud_speech_runtime_owner_cancel(&owner) == CLOUD_SPEECH_EBUSY);
  CHECK(cloud_speech_runtime_owner_poll(&owner) == CLOUD_SPEECH_EBUSY);
  owner.speech.busy = false;
  CHECK(cloud_speech_runtime_owner_cancel(&owner) == 0);
  CHECK(owner.speech.readiness == 0 && fake.cloud_calls == 0);
  puts("cloud speech runtime owner: 7 groups passed");
  return 0;
}
