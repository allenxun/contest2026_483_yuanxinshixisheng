# Versioned Wi-Fi lease and cloud startup gate candidate

This isolated candidate implements the C1 control contract proposed by
`../cloud-handoff-review-20260913`. It is fixed-capacity, performs no heap
allocation, makes no network call, contains no endpoint or credential, and does
not modify formal `app/`, `board/`, or `port/` source.

## Contract

`vv_lease_publish_acquired()` copies an interface name, IPv4 address, gateway,
and the raw DHCP option-6 payload into a value snapshot. Option 6 may contain
zero, one, or two IPv4 DNS addresses. Zero DNS preserves the distinction between
"Wi-Fi obtained an address" and "cloud DNS may start": the lease is online, but
`vv_cloud_begin_dns()` returns `VV_LEASE_NO_DNS` and the supervisor remains at
`LEASE_READY`.

All address scalars in this candidate use canonical big-endian notation (for
example `10.3.0.1 == 0x0a030001`). A future adapter at the formal `struct in_addr`
boundary must use `ntohl()`/`htonl()` explicitly rather than relying on host
integer representation.

Each successful acquire increments `generation`. Disconnect increments it
again before publishing an entirely cleared offline snapshot. A cancellation
token is true when explicitly cancelled, when link/DHCP is down, or when the
store generation differs from the captured generation. Therefore the first
check after disconnect cancels synchronously; no polling sleep is required.

`vv_cloud_supervisor` permits this ordered transition only:

```text
OFFLINE -> LEASE_READY -> DNS_PROBING -> DNS_READY
        -> TRUST_READY -> TLS_PROBING -> CLOUD_READY
```

Any offline snapshot resets it to `OFFLINE`. Any new online generation resets it
to `LEASE_READY`, so reconnect cannot inherit DNS, trust, or TLS results from the
prior lease. Completion events with an old generation return `VV_LEASE_STALE`.
The supervisor holds a read-only reference to the lease store. Every transition
and `vv_cloud_can_start_request()` rechecks the store itself, so a disconnect
cancels the start gate even before an explicit supervisor observation. The final
gate checks current snapshot validity, DNS availability, `CLOUD_READY`, and
exact generation.

## Concurrency boundary

The candidate deliberately contains no OS lock. Formal radio code must call the
publish and copy functions while holding its existing `g_wifi_ip_state` mutex.
The DNS/HTTPS cancel adapter must briefly acquire that same mutex around
`vv_lease_cancelled()`; direct concurrent access would be a C data race.
The first cloud worker remains serialized, matching the current global NuttX DNS
backend context. If a later caller needs lock-free observation, add a platform
adapter around this value contract; do not expose internal DHCP pointers.

## Host verification

Run from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_host_tests.ps1
```

The script compiles the C implementation and links it from C++ at both `-O0`
and `-O2`, with pedantic warnings treated as errors. Tests cover snapshot copy,
option-6 parsing and validation, no-DNS rejection, startup ordering, stale
generation rejection, immediate disconnect cancellation, explicit cancellation,
and reconnect with a new generation. The deterministic result records
`cancellation_observation_ms=0` because cancellation is observed in the same
call stack, satisfying the proposed `<100 ms` gate without wall-clock timing.

## Formal integration points (recorded, not applied)

1. `app/k7radio/skw_netdev.c`: after DHCP IP/netmask/router application, copy
   `dhcpc_state.dnsaddr` as option 6; register validated DNS with the NuttX DNS
   API. If the SDK exposes only one DNS address, publish one. Never substitute
   the gateway when option 6 is absent.
2. `app/k7radio/wifi_ip_service.inc`: place the lease store beside the current
   IP state, publish acquire while holding `g_wifi_ip_state`, and copy snapshots
   through a public read-only API. During cleanup, clear NuttX DNS first, then
   publish disconnect while holding the same lock.
3. `app/k7radio/k7_radio_service.h`: expose a copied snapshot API compatible
   with `k7_radio_network_snapshot(out)`; expose no password, DHCP pointer, or
   mutable global.
4. `app/k7agent/cloud/src/vv_dns_nuttx.c`: initialize one cancellation token per
   request from the observed lease generation and bridge `vv_lease_cancelled()`
   into the existing DNS/HTTPS cancellation callbacks.
5. A separate cloud supervisor task owns the candidate state machine. It may
   begin DNS only with a same-generation lease containing option 6, and it must
   repeat DNS/trust/TLS gates after reconnect before accepting ASR/TTS work.

These integration points remain unapplied until the accepted speech firmware
and combined profile are ready. This candidate does not prove NuttX compilation,
DNS registration, board DNS, Internet reachability, TLS, or MiMo service access.
