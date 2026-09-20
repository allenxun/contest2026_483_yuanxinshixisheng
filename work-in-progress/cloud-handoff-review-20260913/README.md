# Voice provisioning to MiMo cloud handoff review

Review date: 2026-09-13. Branch observed: `dev-ai-contest-2026`.

This is a read-only architecture review. It changes no formal source, does not
call a network endpoint, does not use or record a credential, and does not touch
the board. Formal paths below are the evidence for every current-state claim.

## Result

The shortest safe route is **not** to extend the provisioning `Controller` into
a cloud client. Provisioning should still finish at a real DHCP/IP event. A
small, separately owned `CloudSupervisor` should then bind every DNS/TLS/API
operation to a versioned Wi-Fi lease. This preserves offline provisioning and
lets link loss cancel an in-flight cloud request without reopening the password
or radio state machines.

The repository already contains bounded DNS and HTTPS cores, but there is no
end-to-end network request. The current board snapshot is offline and the new
ASR/TTS-gated provisioning firmware is pending hardware validation
([`project-manifest.json:99`](../../project-manifest.json),
[`project-manifest.json:104`](../../project-manifest.json),
[`project-manifest.json:123`](../../project-manifest.json),
[`project-manifest.json:357`](../../project-manifest.json)). The cloud/Agent
plan is also explicitly not deployed
([`project-manifest.json:438`](../../project-manifest.json)).

## Proposed state machine

```text
OFFLINE_PROVISIONING
  | VoiceLink receives a matching IpReady transaction
  v
WIFI_LEASE_READY
  | snapshot = {generation, interface, IPv4, gateway, DNS[]}
  v
DNS_INSTALLING -> DNS_PROBING -> DNS_READY
  |                         failure/link change -> OFFLINE_PROVISIONING
  v
TRUST_PREFLIGHT
  | approved entropy + trusted wall time + CA + endpoint/config pair
  v
TLS_PROBING -> CLOUD_READY
  |              link generation changes -> CANCEL -> OFFLINE_PROVISIONING
  +--> CAPTURE -> WAV -> MIMO_ASR -> TRANSCRIPT
  +--> TEXT -> MIMO_TTS -> WAV_VALIDATE/CONVERT -> SPEAKER
```

`WIFI_LEASE_READY` is stronger than a syntactically valid IP address. It must
name the lease generation that owns the interface, route and DNS servers. Every
cloud cancellation token checks that generation. This is required because the
current VoiceLink code releases its connection transaction immediately after
`IpReady` and enters a terminal state
([`app/voicelink/src/core.cpp:425`](../../app/voicelink/src/core.cpp),
[`app/voicelink/src/voice_loop.cpp:188`](../../app/voicelink/src/voice_loop.cpp)).

## What exists and what is missing

| Layer | Existing evidence | Missing minimum interface / behavior |
| --- | --- | --- |
| Provisioning completion | `ConnectStatus::IpReady` validates an IPv4 address and moves to `Completed` ([`app/voicelink/src/core.cpp:425`](../../app/voicelink/src/core.cpp)). | Publish a versioned lease snapshot to a separate cloud supervisor. Do not make cloud readiness part of Wi-Fi success. |
| DHCP application | The driver copies the DHCP lease and applies only IPv4, netmask and default route ([`app/k7radio/skw_netdev.c:118`](../../app/k7radio/skw_netdev.c), [`app/k7radio/skw_netdev.c:137`](../../app/k7radio/skw_netdev.c)). | Extract DHCP option 6 from the SDK lease, validate 1–2 IPv4 DNS addresses, register them with NuttX, and clear them when this lease ends. |
| Link lifecycle | The IP worker stores only printable IP/gateway and clears both during cleanup ([`app/k7radio/wifi_ip_service.inc:37`](../../app/k7radio/wifi_ip_service.inc), [`app/k7radio/wifi_ip_service.inc:74`](../../app/k7radio/wifi_ip_service.inc)). The public service exposes only connection dispatch and scan handles ([`app/k7radio/k7_radio_service.h:6`](../../app/k7radio/k7_radio_service.h)). | Add a copied read-only snapshot: generation, link/DHCP flags, interface name, IPv4, gateway, DNS list. Increment generation on acquire and teardown; never expose internal pointers or credentials. |
| DNS policy | Bounded hostname, deadline, cancellation and retry policy exist ([`app/k7agent/cloud/include/vv_dns_client.h:12`](../../app/k7agent/cloud/include/vv_dns_client.h), [`app/k7agent/cloud/src/vv_dns_client.c:65`](../../app/k7agent/cloud/src/vv_dns_client.c)). The NuttX backend calls IPv4 `getaddrinfo` and enforces the configured resolver bound ([`app/k7agent/cloud/src/vv_dns_nuttx.c:24`](../../app/k7agent/cloud/src/vv_dns_nuttx.c), [`app/k7agent/cloud/src/vv_dns_nuttx.c:80`](../../app/k7agent/cloud/src/vv_dns_nuttx.c)). | Bind cancellation to lease generation. The current backend uses one static context, so first implementation should own one serialized cloud worker or replace it with caller-owned context before concurrency. |
| HTTPS/1.1 core | Request/response limits, total deadline, cancellation, secure temporary-buffer clearing, TLS verification and SNI checks exist ([`app/k7agent/cloud/include/vv_https_client.h:39`](../../app/k7agent/cloud/include/vv_https_client.h), [`app/k7agent/cloud/src/vv_https_client.c:385`](../../app/k7agent/cloud/src/vv_https_client.c)). | Implement the required bounded nonblocking TCP connector. It must poll connect completion, check `SO_ERROR`, and cancel on deadline or lease-generation change. |
| TLS transport | The mbedTLS adapter requires caller-provided CA, TCP connect, security-ready gate and monotonic clock ([`app/k7agent/cloud/include/vv_https_mbedtls.h:16`](../../app/k7agent/cloud/include/vv_https_mbedtls.h), [`app/k7agent/cloud/src/vv_https_mbedtls.c:160`](../../app/k7agent/cloud/src/vv_https_mbedtls.c)). It requires SNI and zero verify flags ([`app/k7agent/cloud/src/vv_https_mbedtls.c:79`](../../app/k7agent/cloud/src/vv_https_mbedtls.c), [`app/k7agent/cloud/src/vv_https_mbedtls.c:97`](../../app/k7agent/cloud/src/vv_https_mbedtls.c)). | Supply and independently verify entropy, trusted wall time and a minimal CA bundle. Current cloud config explicitly lacks timekeeping, `/dev/urandom`, and RTC ([`board/kickpi_k7/configs/velavision_cloud_probe_local/defconfig:364`](../../board/kickpi_k7/configs/velavision_cloud_probe_local/defconfig), [`:536`](../../board/kickpi_k7/configs/velavision_cloud_probe_local/defconfig), [`:562`](../../board/kickpi_k7/configs/velavision_cloud_probe_local/defconfig)). |
| Cloud command | `k7cloud status` deliberately exercises validation only and prints `network_request=disabled` ([`app/k7agent/cloud/src/k7cloud_main.c:17`](../../app/k7agent/cloud/src/k7cloud_main.c), [`app/k7agent/cloud/src/k7cloud_main.c:41`](../../app/k7agent/cloud/src/k7cloud_main.c)). | Add explicit `dns-probe`, `tls-probe`, and later `mimo-asr` / `mimo-tts` diagnostic entries. Each command must fail closed when an earlier gate is absent. |
| MiMo protocol | No endpoint, model name or credential exists under formal `app/`. The reviewed specification says ASR and TTS use `POST {base_url}/chat/completions`, with ASR text at `choices[0].message.content` and nonstream TTS audio at `choices[0].message.audio.data` ([`work-in-progress/mimo-api-spec-20260913/README.md:7`](../mimo-api-spec-20260913/README.md), [`:66`](../mimo-api-spec-20260913/README.md), [`:104`](../mimo-api-spec-20260913/README.md)). | Implement bounded official nested JSON encoders/decoders and Base64. Keep the existing isolated flat codec out of formal code because it is a test fixture, not the Xiaomi wire schema. |
| Audio handoff | Local VoiceLink already owns microphone ASR and TTS/speaker paths. | First cloud milestone reuses one bounded capture, wraps PCM16 as WAV, posts nonstream ASR, then requests nonstream TTS WAV and converts only after validating its `fmt`/`data` chunks. Serialize capture/playback with the existing audio owner and keep offline local provisioning available. |
| Agent/tools | Tool API supports a software ledger, but only read-only `Capabilities` and `WifiStatus` validate; other tools are unsupported and the adapter is absent ([`app/k7agent/tool_api/dispatcher.hpp:10`](../../app/k7agent/tool_api/dispatcher.hpp), [`app/k7agent/tool_api/dispatcher.hpp:24`](../../app/k7agent/tool_api/dispatcher.hpp), [`app/k7agent/tool_api/README.md:5`](../../app/k7agent/tool_api/README.md)). | Cloud ASR/TTS readiness must not be reported as Agent readiness. A later intent-model loop and real device adapters need separate acceptance. |
| Build profile | The spoken-TTS profile enables staged VoiceLink assets but has mbedTLS disabled ([`board/kickpi_k7/configs/velavision_spoken_tts_local/defconfig:1591`](../../board/kickpi_k7/configs/velavision_spoken_tts_local/defconfig), [`:2737`](../../board/kickpi_k7/configs/velavision_spoken_tts_local/defconfig)); the cloud profile enables mbedTLS/k7cloud but not staged VoiceLink assets ([`board/kickpi_k7/configs/velavision_cloud_probe_local/defconfig:2733`](../../board/kickpi_k7/configs/velavision_cloud_probe_local/defconfig), [`:2744`](../../board/kickpi_k7/configs/velavision_cloud_probe_local/defconfig), [`:2749`](../../board/kickpi_k7/configs/velavision_cloud_probe_local/defconfig)). | Create one derived integration profile only after the repaired speech image passes. It must preserve the audited ASR/TTS arena layout while enabling DNS/mbedTLS/cloud symbols; a cloud-only probe image cannot establish speech integration. |

## Minimal interfaces

These are contracts to implement, not changes made by this review.

```c
struct k7_network_snapshot {
  uint64_t generation;
  bool link_up;
  bool dhcp_ready;
  char ifname[IFNAMSIZ];
  struct in_addr ipv4;
  struct in_addr gateway;
  struct in_addr dns[2];
  size_t dns_count;
};

int k7_radio_network_snapshot(struct k7_network_snapshot *out);
```

Snapshot rules:

- copy under the existing IP-state lock; no borrowed pointer;
- `generation` changes before publishing a new lease and again before teardown;
- teardown clears DNS registration before publishing `dhcp_ready=false`;
- the cloud cancel callback returns true when the captured generation differs,
  link is down, or the caller explicitly cancels;
- logs may contain state, generation, public endpoint host and numeric errors;
  never token, password, transcript, prompt, Base64, or audio bytes.

The first cloud worker can remain serialized. That matches the global NuttX DNS
backend context in [`app/k7agent/cloud/src/vv_dns_nuttx.c:34`](../../app/k7agent/cloud/src/vv_dns_nuttx.c)
and avoids inventing unsupported parallel DNS semantics.

## Minimal delivery sequence and acceptance gates

1. **C0 — finish local voice provisioning firmware acceptance.** This is the
   prerequisite, not cloud work. Pass only when TTS→ASR→TTS releases the shared
   arena, real voice selection/password reaches a genuine `IpReady`, and the
   user hears the success prompt. Current pending image is not hardware tested.

2. **C0A — create and audit the combined firmware profile.** Derive it from the
   accepted spoken-TTS configuration, add only the required DNS/mbedTLS/k7cloud
   options, then rebuild and recheck model addresses, ELF symbols, heap/stack
   budgets and the RAM-only package. Passing this build does not count as a
   network test.

3. **C1 — lease and DNS plumbing.** Add the snapshot/generation contract and
   option-6 registration. With a controlled DHCP lease, the snapshot must match
   the real interface/IP/gateway/DNS; after forced disconnect, DNS is cleared,
   generation changes, and an old-generation cancellation token fires within
   100 ms. No password may occur in logs or snapshots.

4. **C2 — board DNS probe.** After C1, resolve one configured public hostname
   through `vv_dns_resolve_ipv4`. Pass with nonzero IPv4, attempts ≤ 3 and total
   time within policy. Negative gates: malformed host rejected without network;
   link loss cancels; unknown name does not return a stale prior address.

5. **C3 — trust preflight.** Select an approved RK3576 entropy source, trusted
   wall-time source and minimal CA bundle for the selected endpoint. Pass only
   when two reboot-separated DRBG probes are not deterministic, wall time is
   within a documented tolerance and survives the chosen trust policy, and
   expired/not-yet-valid/wrong-host/untrusted-chain fixtures all fail.

6. **C4 — bounded TCP/TLS probe without credentials.** Implement nonblocking
   connect and run an HTTPS request with no Authorization header. Pass only with
   SNI true, peer cert present, verify flags zero, bounded completion, and clean
   cancellation on link loss. A reachable HTTP 4xx can prove transport; it does
   not prove API entitlement.

7. **C5 — official MiMo nonstream codec on host.** Atomically configure the
   exact Token Plan base URL and matching credential type at runtime. Golden
   tests must cover the official nested ASR and TTS shapes, JSON escaping,
   Base64 limits, truncated/duplicate/wrong-type fields, non-200 responses, and
   zero partial output. Fixture corpus and logs contain no real credential.

8. **C6 — one redacted board ASR call.** Capture at most 5 seconds of 16 kHz,
   mono PCM16, create a valid WAV, keep encoded request below the official
   10 MB Base64 limit, and inject the token at runtime. Pass only when a 2xx
   response yields a bounded UTF-8 transcript, request buffers are erased, and
   a full evidence scan finds no token/audio/transcript bytes in serial logs.

9. **C7 — one redacted board TTS call and playback.** Request nonstream WAV with
   an explicit Chinese voice, validate RIFF/WAVE plus bounded `fmt` and `data`,
   convert to the board playback format, and play once. Pass only when API and
   WAV validation succeed, audio owner/codec restore succeed, buffers are
   erased, and the user confirms the expected phrase is audible.

10. **C8 — cloud speech supervisor and fallback.** Run ASR/TTS only in
   `CLOUD_READY`. Force link loss during DNS, handshake, upload, response and
   playback; every network phase must terminate within its deadline, release
   resources and return to offline/local behavior. Reconnect creates a new
   generation and requires DNS/trust/TLS gates again.

C0A, C1, the C3 platform-source investigation, and C5 host codec work can proceed in
parallel after C0's source has stabilized. C2 depends on C0A and C1; C4 depends on C2
and C3; C6/C7 depend on C4 and C5; C8 depends on C6 and C7.

## Explicit non-claims

- The existing host tests and ARM64 link evidence do not prove board DNS,
  internet reachability, TLS, MiMo entitlement, ASR, or TTS.
- A DHCP IP does not prove DNS or Internet access.
- A successful ASR/TTS call does not prove an Agent or any physical tool call.
- The Token Plan region must come from runtime account configuration; it cannot
  be inferred from the credential prefix alone. Credentials remain runtime-only.
- Cloud ASR/TTS cannot replace the local first-connect path because the cloud is
  unreachable before provisioning succeeds
  ([`work-in-progress/mimo-api-spec-20260913/README.md:153`](../mimo-api-spec-20260913/README.md)).
