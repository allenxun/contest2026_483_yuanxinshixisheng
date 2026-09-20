#include <nuttx/config.h>

#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "vv_dns_client.h"
#include "vv_dns_nuttx.h"
#include "vv_https_client.h"
#include "vv_https_mbedtls.h"

#ifdef K7CLOUD_MIMO_V25
#  include "mimo_v25_profile.h"
#endif

#ifdef K7CLOUD_SPEECH_ORCHESTRATOR
#  include "cloud_speech_mimo_adapter.h"
#endif

static void usage(void)
{
  puts("usage: k7cloud status");
#ifdef K7CLOUD_MIMO_V25
  puts("       k7cloud mimo-profile <regional-host>");
#endif
#ifdef K7CLOUD_SPEECH_ORCHESTRATOR
  puts("       k7cloud speech-status");
#endif
}

static int link_status(void)
{
  struct vv_dns_result dns_result;
  struct vv_https_response response;

  /* Exercise only the public argument-validation paths.  These calls keep the
   * production adapter sections in the ELF without opening a socket, seeding a
   * DRBG or accepting any endpoint or credential. */
  if (strcmp(vv_dns_status_name(VV_DNS_OK), "ok") != 0 ||
      vv_dns_resolve_ipv4(NULL, NULL, NULL, &dns_result) !=
        VV_DNS_INVALID_ARGUMENT ||
      vv_dns_nuttx_backend_init(NULL, NULL) != -EINVAL ||
      strcmp(vv_https_strerror(VV_HTTPS_OK), "ok") != 0 ||
      vv_https_perform(NULL, NULL, NULL, NULL, NULL, &response) !=
        VV_HTTPS_EINVAL ||
      vv_https_mbedtls_create(NULL) != NULL)
    {
      puts("K7CLOUD link_selftest=failed");
      return 1;
    }

  puts("K7CLOUD DNS=linked HTTPS=linked");
  puts("K7CLOUD link_selftest=passed");
  puts("K7CLOUD entropy=unverified wall_time=unverified ca=unset");
  puts("K7CLOUD network_request=disabled");
#ifdef K7CLOUD_MIMO_V25
  puts("K7CLOUD mimo_v25=linked token=unset");
#else
  puts("K7CLOUD mimo_v25=disabled");
#endif
#ifdef K7CLOUD_SPEECH_ORCHESTRATOR
  puts("K7CLOUD speech_orchestrator=linked runtime=not_configured");
#else
  puts("K7CLOUD speech_orchestrator=disabled");
#endif
  return 0;
}

#ifdef K7CLOUD_MIMO_V25
static int profile_status(const char *host)
{
  struct mimo_cloud_protocol protocol;

  if (mimo_v25_profile_init(&protocol, host) != MIMO_CLOUD_OK ||
      strcmp(protocol.asr_model, "mimo-v2.5-asr") != 0 ||
      strcmp(protocol.tts_model, "mimo-v2.5-tts") != 0 ||
      protocol.port != 443)
    {
      puts("K7CLOUD mimo_profile=invalid");
      return 1;
    }

  /* Do not echo the caller's regional host.  This command validates the
   * profile only and deliberately accepts no token or network operation. */
  puts("K7CLOUD mimo_profile=valid asr=mimo-v2.5-asr tts=mimo-v2.5-tts");
  puts("K7CLOUD token=unset network_request=disabled");
  return 0;
}
#endif

#ifdef K7CLOUD_SPEECH_ORCHESTRATOR
static int speech_status(void)
{
  struct cloud_speech_ops ops;
  struct cloud_speech_orchestrator orchestrator;
  unsigned char wav_scratch[46];
  int16_t pcm_scratch[1];

  if (cloud_speech_mimo_adapter_ops(&ops) != CLOUD_SPEECH_OK ||
      ops.play_fixed_prompt == NULL || ops.cloud_asr_wav == NULL ||
      ops.cloud_tts_wav == NULL || ops.play_pcm16_16k == NULL ||
      cloud_speech_init(&orchestrator, &ops, NULL, wav_scratch,
                        sizeof(wav_scratch), pcm_scratch, 1) !=
        CLOUD_SPEECH_OK || cloud_speech_is_ready(&orchestrator))
    {
      puts("K7CLOUD speech_adapter=failed");
      return 1;
    }

  puts("K7CLOUD speech_adapter=linked audio=pcm16le/16000/mono");
  puts("K7CLOUD readiness=0x00 required=0xff cloud_ready=0");
  puts("K7CLOUD runtime=not_configured network_request=disabled");
  return 0;
}
#endif

int main(int argc, char **argv)
{
  if (argc == 2 && strcmp(argv[1], "status") == 0)
    {
      return link_status();
    }

#ifdef K7CLOUD_MIMO_V25
  if (argc == 3 && strcmp(argv[1], "mimo-profile") == 0)
    {
      return profile_status(argv[2]);
    }
#endif

#ifdef K7CLOUD_SPEECH_ORCHESTRATOR
  if (argc == 2 && strcmp(argv[1], "speech-status") == 0)
    {
      return speech_status();
    }
#endif

  usage();
  return 2;
}
