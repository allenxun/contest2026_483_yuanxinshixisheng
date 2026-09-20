# MiMo cloud speech client candidate (host-only)

This isolated candidate adds bounded Xiaomi MiMo v2.5 speech requests to the
reviewed `app/k7agent/cloud` HTTPS client. It contains no API key, performs no
network request, changes no formal source, and does not touch the board.

## Implemented behavior

- The token is supplied for each call and exists only in a securely cleared
  temporary Authorization buffer.
- Request and response bodies have independent hard limits and are cleared
  before release.
- Cancellation and one absolute request deadline come from
  `vv_https_perform`; TLS certificate, hostname and verification requirements
  remain mandatory in that layer.
- Non-200 responses, oversized bodies, malformed UTF-8, malformed JSON and
  invalid WAV containers are rejected.
- Response data is completely collected and validated before caller-visible
  output is committed.
- Logging accepts only fixed event names and integer counts. Tests confirm that
  tokens, transcripts, prompt text and encoded audio do not enter logs.
- `mimo_v25_profile_init()` installs the official non-streaming MiMo v2.5 ASR
  and TTS Chat Completions profile. The host remains a runtime choice, so a
  Token Plan credential can be paired with its exact regional endpoint.
- ASR sends one complete WAV/MP3 as pure Base64 with an explicit `format`,
  `asr_options.language: zh`, and `stream: false`. The conservative decimal
  10 MB encoded-audio limit is enforced before request construction.
- TTS sends spoken text as an `assistant` message, requests an explicit voice
  and non-streaming WAV, and sets `stream: false`.
- Nested response decoders locate `choices[0].message.content` and
  `choices[0].message.audio.data`. They validate the complete JSON envelope,
  Unicode escapes, canonical Base64 and RIFF/WAVE chunks before copying output.
  Duplicate target fields, trailing JSON, embedded NUL transcripts, malformed
  padding and invalid WAV containers are rejected without partial output.

## Official non-streaming profile

The adjacent `../mimo-api-spec-20260913/` record is the source of truth. It was
compiled from Xiaomi MiMo official API documentation and the XiaomiMiMo
official repository. Both models use `POST /chat/completions`, OpenAI-compatible
Chat Completions JSON, and exactly one authentication header. This candidate
uses the officially supported `Authorization: Bearer` form.

Initialize the profile with a host name only, without a scheme or path:

```c
struct mimo_cloud_protocol protocol;
int rc = mimo_v25_profile_init(
  &protocol, "token-plan-cn.xiaomimimo.com");
```

The example host is illustrative. Token Plan deployments must use the exact
regional host displayed in their console; pay-as-you-go and Token Plan
endpoints cannot be mixed. The caller injects the token into each request at
runtime. The initializer and profile never store a credential.

The request structures are:

```json
{"model":"mimo-v2.5-asr","messages":[{"role":"user","content":[{"type":"input_audio","input_audio":{"data":"<base64>","format":"wav"}}]}],"asr_options":{"language":"zh"},"stream":false}
```

```json
{"model":"mimo-v2.5-tts","messages":[{"role":"assistant","content":"<text>"}],"audio":{"format":"wav","voice":"冰糖"},"stream":false}
```

ASR response text is decoded from `choices[0].message.content`. TTS Base64 WAV
is decoded from `choices[0].message.audio.data`. The generic flat-JSON codec
remains a deterministic test/private-gateway fixture and is not used by the
MiMo v2.5 profile.

## Capacity and format boundaries

The service documents a 10 MB limit on the encoded ASR audio string without
specifying decimal or binary units. `MIMO_V25_MAX_ASR_BASE64_BYTES` uses the
smaller decimal value of 10,000,000 bytes. Therefore the largest raw payload
whose Base64 can fit is 7,500,000 bytes. The caller's request-body limit must
also include the JSON envelope.

For `wav`, the encoder checks a complete RIFF/WAVE layout containing exactly
one valid `fmt ` chunk and one `data` chunk. `mp3` is accepted as the other
official input format, while PCM-only labels are rejected. Non-streaming TTS
accepts only a Base64-decoded valid WAV. The board's planned 16 kHz, mono,
PCM16 capture is an implementation choice that still needs a live service
compatibility check because the official API does not promise those exact WAV
parameters.

## Host verification

Run:

```powershell
./run_host_tests.ps1
```

GCC `-O0` and `-O2`, with `-Wall -Wextra -Werror -pedantic`, each pass 12
groups. The original six cover generic transport and request safety. The six
MiMo groups cover official ASR/TTS request shapes, raw and escaped Unicode,
escaped Base64 characters, canonical Base64 and WAV validation,
duplicate/trailing response rejection, the exact encoded-audio limit, hostile
host rejection, runtime redaction, and no partial output commit.

The installed MinGW toolchain does not provide ASan/UBSan runtime libraries,
so sanitizer execution remains unavailable and is not reported as passed.

## Integration boundary

Before promoting this candidate into `app/`, select the account's exact
endpoint host, set conservative board request/response limits, provide trusted
time, CA, entropy and TCP prerequisites required by the HTTPS layer, and run a
redacted real-network test. The account's model entitlement, live WAV
compatibility and latency remain unverified. API keys must stay runtime-only.
Host fake responses do not establish DNS, TLS, Xiaomi API, billing-plan,
latency or board acceptance.

Official sources and observations are recorded in:

- `../mimo-api-spec-20260913/README.md`
- `../mimo-api-spec-20260913/mimo-v2.5-audio-api.json`
