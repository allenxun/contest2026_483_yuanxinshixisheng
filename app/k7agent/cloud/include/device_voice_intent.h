#ifndef K7_DEVICE_VOICE_INTENT_H
#define K7_DEVICE_VOICE_INTENT_H
#include <stddef.h>
enum k7_voice_intent { K7_VOICE_NONE, K7_VOICE_TRACK, K7_VOICE_PHOTO,
                       K7_VOICE_STOP, K7_VOICE_QUIET };
struct k7_voice_result {
  enum k7_voice_intent intent;
  unsigned finals;
  int ambiguous, completed;
};
/* Only complete, exact command finals are eligible; never return shell text. */
int k7_voice_event(struct k7_voice_result *, const char *, size_t);
enum k7_voice_intent k7_voice_result_intent(const struct k7_voice_result *);
#endif
