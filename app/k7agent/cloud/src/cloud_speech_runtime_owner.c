#include "cloud_speech_runtime_owner.h"

#include <string.h>

static int available(struct cloud_speech_runtime_owner *owner)
{
  if (!owner || !owner->initialized) return CLOUD_SPEECH_EINVAL;
  if (owner->dispatching || owner->speech.busy) return CLOUD_SPEECH_EBUSY;
  return CLOUD_SPEECH_OK;
}

int cloud_speech_runtime_owner_init(
  struct cloud_speech_runtime_owner *owner,
  const struct cloud_speech_ops *ops, void *ops_arg,
  unsigned char *wav_scratch, size_t wav_capacity,
  int16_t *pcm_scratch, size_t pcm_frames,
  int (*read_radio)(void *, struct cloud_speech_radio_snapshot *),
  void *radio_arg)
{
  int rc;
  if (!owner) return CLOUD_SPEECH_EINVAL;
  memset(owner, 0, sizeof(*owner));
  if (!read_radio) return CLOUD_SPEECH_EINVAL;
  rc = cloud_speech_init(&owner->speech, ops, ops_arg, wav_scratch,
                        wav_capacity, pcm_scratch, pcm_frames);
  if (rc) return rc;
  rc = cloud_speech_radio_bridge_init(&owner->radio, &owner->speech);
  if (rc) return rc;
  owner->read_radio = read_radio;
  owner->radio_arg = radio_arg;
  owner->initialized = true;
  return CLOUD_SPEECH_OK;
}

int cloud_speech_runtime_owner_poll(struct cloud_speech_runtime_owner *owner)
{
  struct cloud_speech_radio_snapshot snapshot = {0};
  int rc = available(owner);
  if (rc) return rc;
  if (!owner->running) return CLOUD_SPEECH_ENOTREADY;
  owner->dispatching = true;
  rc = owner->read_radio(owner->radio_arg, &snapshot);
  if (!rc) rc = cloud_speech_radio_bridge_apply(&owner->radio, &snapshot);
  /* A missing snapshot or failed local prompt is not a ready connection.
   * The bridge retains its generation high-water mark across recovery. */
  if (rc) (void)cloud_speech_set_network(&owner->speech, false, false);
  owner->last_error = rc;
  owner->dispatching = false;
  return rc;
}

int cloud_speech_runtime_owner_start(struct cloud_speech_runtime_owner *owner)
{
  int rc = available(owner);
  if (rc) return rc;
  if (owner->running) return CLOUD_SPEECH_EBUSY;
  (void)cloud_speech_set_network(&owner->speech, false, false);
  owner->running = true;
  return cloud_speech_runtime_owner_poll(owner);
}

int cloud_speech_runtime_owner_cancel(struct cloud_speech_runtime_owner *owner)
{
  int rc = available(owner);
  if (rc) return rc;
  owner->running = false;
  owner->last_error = 0;
  return cloud_speech_set_network(&owner->speech, false, false);
}

bool cloud_speech_runtime_owner_ready(
  const struct cloud_speech_runtime_owner *owner)
{
  return owner && owner->initialized && owner->running &&
         !owner->dispatching && !owner->last_error &&
         cloud_speech_is_ready(&owner->speech);
}
