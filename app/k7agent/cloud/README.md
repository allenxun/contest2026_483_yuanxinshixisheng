# K7 cloud connectivity core

This directory contains the reviewed bounded DNS policy and HTTPS/1.1 client
for the later MiMo cloud Agent path. `EXAMPLES_K7CLOUD` is off by default.
The first command, `k7cloud status`, only proves that the ARM64 image links the
DNS and Mbed TLS adapters; it does not open a socket or accept credentials.
When the optional profiles are compiled, the same command reports whether the
MiMo and speech coordinator objects are linked. `k7cloud mimo-profile HOST`
validates a caller-supplied Token Plan regional hostname without retaining or
printing it. `k7cloud speech-status` validates the MiMo/k7sound adapter and
prints the closed eight-gate runtime state. All three commands are offline
diagnostics: none accepts a token, opens a socket or claims cloud readiness.

The DNS resolver must run in a separate cloud task after the shared Wi-Fi
service has applied a DHCP lease and registered option 6. Link loss cancels the
request. The HTTPS adapter requires all of these gates before construction:

- an approved RK3576 entropy source;
- trusted wall time for X.509 validity checks;
- a caller-owned minimal CA bundle;
- a bounded, cancellation-aware TCP connector.

TLS verification is mandatory and includes SNI, a peer certificate and zero
verification flags. Request and response sizes are bounded, redirects and
retries are caller policy, and sensitive staging buffers are cleared. API keys,
hostnames and MiMo protocol values are deliberately absent from this source.

Provenance:

- DNS: `work-in-progress/parallel-dns-client-sol`
- HTTPS: `work-in-progress/parallel-https-client-sol`
- SDK audit: `work-in-progress/parallel-dns-https-audit-sol`

Host policy tests are rerun from `tests/k7cloud/run_host_tests.ps1`. ARM64
linking, board DNS and TLS remain separate acceptance stages.

The optional `EXAMPLES_K7CLOUD_MIMO_V25` sources implement the official
non-streaming MiMo v2.5 ASR/TTS Chat Completions request shape and strict
response decoding. The option is off by default and contains no endpoint
choice or credential. Token Plan deployments must inject the exact regional
host and token together at runtime after DNS, entropy, trusted time, CA and
TLS gates pass. Host tests cover nested JSON, Unicode, canonical Base64, WAV,
the decimal 10 MB encoded-audio limit, bounded output and log redaction; they
do not prove board networking or account entitlement.

`EXAMPLES_K7CLOUD_SPEECH_ORCHESTRATOR` adds an opt-in batch speech state
machine. It accepts cloud work only after the caller reports live Wi-Fi, IPv4,
DNS, entropy, trusted time, CA, TCP and API readiness. The Wi-Fi connected
transition plays a caller-owned 16 kHz mono prompt through `k7sound` before
cloud readiness, so the confirmation never depends on MiMo. ASR accepts only
16 kHz mono PCM16LE (wrapped locally as WAV) or an equivalent WAV. MiMo TTS WAV
at 16/24 kHz is validated, converted to 16 kHz mono PCM16LE and then passed to
`k7sound`. Tokens remain borrowed request arguments and are neither retained
nor logged. This module uses the current non-streaming profile and makes no
streaming claim.

`EXAMPLES_K7CLOUD_RADIO_READINESS` is a further opt-in bridge to the public
`k7radio_get_link_snapshot()` API. The snapshot is copied while the radio's
DHCP state lock is held and carries a monotonic link generation. It reports a
connected link only while the native worker owns a valid non-link-local IPv4
lease. Applying a newer offline snapshot clears all stale cloud gates. A
regressed generation, contradictory state or invalid IPv4 fails closed. This
bridge never sets DNS, entropy, trusted time, CA, TCP or API readiness.
