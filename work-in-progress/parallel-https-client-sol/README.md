# VelaVision bounded HTTPS client candidate

This directory is an isolated, host-tested candidate for one HTTPS/1.1 request
at a time on RK3576 openvela. It implements request streaming, mandatory TLS
verification gates, SNI evidence, a total monotonic deadline, cancellation,
bounded response framing, decoded `Content-Length`/chunked/EOF bodies and
deterministic cleanup. It contains no DNS, MiMo, ASR, TTS or Agent behavior.

## Interface

`include/vv_https_client.h` is independent of Mbed TLS. The request body source
is called with an offset and a bounded destination buffer. The response sink
receives decoded body bytes incrementally. The transport contract accepts the
same absolute deadline and cancellation token on connect/read/write. A request
is rejected before HTTP bytes are sent unless the transport reports all three:
SNI applied, peer certificate present and verified, and zero verify flags.

`include/vv_https_mbedtls.h` and `src/vv_https_mbedtls.c` adapt that contract to
Mbed TLS 3.x. The owning network service supplies a cancellation-aware,
deadline-bounded TCP connector; this keeps DNS and network-session ownership
outside this candidate. `security_ready` must return true only after approved
board entropy and trusted wall time are available. `VERIFY_REQUIRED`, the
requested hostname, a caller-provided CA bundle, nonblocking TLS I/O and
`close_notify` are fixed by the adapter.

Logs receive only fixed event names and numeric status. The client never logs
headers, request bytes, response bytes, hostnames or paths. It wipes generated
headers and request staging before release. Callers must wipe their original
Authorization/key and body storage after `vv_https_perform` returns.

The parser rejects CR/LF injection, duplicate conflicting lengths,
Content-Length plus chunked, unsupported transfer codings, oversized headers,
bodies or chunks, malformed/truncated framing, and bodies forbidden by 1xx,
204 or 304. Redirects and retries are not automatic. The caller may inspect the
status and apply an approved same-host HTTPS policy later.

## Host reproduction

From the project root:

```powershell
& .\work-in-progress\parallel-https-client-sol\run_host_tests.ps1
```

The script builds and runs the fake verified-TLS/transport suite with GCC at O0
and O2. Generated executables stay under ignored `out/`. The captured output is
`evidence/host-tests.txt`.

## openvela integration point

1. Copy this candidate into the owning cloud-request component only after
   review. Source `Kconfig` from that component's parent Kconfig.
2. Merge `config/https-client.fragment` into a new RK3576 defconfig, run
   `olddefconfig`, and preserve its final `.config`. The fragment is a candidate,
   not an olddefconfig-validated result.
3. Include `integration.cmake` and call `vv_add_https_client(apps_<owner>)`.
4. Instantiate `vv_https_mbedtls` with a minimal approved CA bundle, the shared
   Wi-Fi service's TCP connector, monotonic clock, and entropy/time readiness
   gate. Run the HTTPS task separately from the Wi-Fi polling worker and BLE
   callbacks.
5. Fill limits from the Kconfig values and keep initial concurrency at one.

No `NETUTILS_WEBCLIENT` dependency is required by this implementation. It uses
the project-local Mbed TLS and POSIX poll/socket layer already available in
openvela. DNS remains the responsibility of the parallel resolver/network
session integration.

## Board work still required

- provide and validate RK3576 cryptographic entropy; xorshift urandom is a hard
  failure, not a fallback;
- provide trusted, rollback-resistant wall time for X.509 validity checks;
- olddefconfig and ARM64 compile/link the adapter against the exact SDK revision;
- bind DHCP DNS/network-session loss to the external TCP connector and cancel;
- select the real MiMo CA roots from its official endpoint chain and document
  subject, validity, rotation and bundle SHA-256;
- test wrong CA, wrong hostname and wrong time, then Content-Length/chunked,
  fragmentation, timeout, disconnect and cancellation against a controlled TLS
  endpoint without credentials;
- measure text/rodata/bss, TLS heap peaks, task stack watermark and cleanup over
  20 requests before any RAM-only, revocable test key is introduced;
- test Wi-Fi/BLE coexistence and network switching. No hardware claim is made by
  this candidate.
