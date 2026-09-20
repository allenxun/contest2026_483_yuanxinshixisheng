# Native VoiceLink Wi-Fi adapter v1

## Scope and minimal change

This is a C++17 adapter to the current formal shared radio service, not ASR/TTS deployment and not target Wi-Fi acceptance. Frozen formal before/after snapshots and SHA256 manifests are retained. `before` was captured before root's required wd_ collision fix; `after` was captured once after it. No formal, SDK, device or old delivery files were modified.

Reuse: old voice-radio-backend-v1 voice_wifi_adapter.cpp/hpp and tests are frozen as old-* with old-inputs.json. Current types/ports/core require no behavioral rewrite: ScanResult request_id/vector/error and ConnectResult/status signatures match; current core cancels known requests, ignores stale results, and wipes its password immediately after beginConnect returns (after/app/voicelink/src/core.cpp:294–296). Default wake words and control-flow evolution do not affect the adapter ABI.

Changes are limited to:

1. All public C `wd_` symbols/types become formal `k7wd_`; filenames and WD_ enum constants unchanged. This avoids NuttX watchdog wd_init collision. Every C object and C++ consumer must use the same current headers.
2. `nativeWifiPort(timeout)` obtains actual k7_wifi_dispatch()/k7_wifi_scans(), checks both published pointers and their immutable association, and returns caller-owned optional SharedWifiPort. It returns nullopt before service publication or for invalid timeout/mismatched service; there is no fallback backend or simulated success. The formal getters use acquire loads of rb_ready; ws_attach completes before publication. No lock, worker, pump or radio operation is added by the factory.
3. Constructor noexcept; conditional exception handling around IPv4 std::string assignment permits the same source to compile with exceptions on/off. Without C++ exceptions, allocation failure can still terminate in the runtime; this is a build compatibility change, not an OOM guarantee. Scan vector/string allocation retains the existing Controller exception boundary where enabled.

## Integration

Copy only candidate/voice_wifi_adapter.cpp and .hpp into the chosen formal VoiceLink source/include location after review. Add that C++ source to the VoiceLink target; include app/voicelink/include, the adapter header directory and app/k7radio. Existing radio C objects must be built from the renamed formal sources, including wifi_broker.c, wifi_dispatch.c, wifi_scan.c, scan_collector.c and existing backend dependencies. Do not compile duplicate radio core copies into a second library. Header wraps radio C declarations in extern C, including service getters.

Enable the actual shared service build and explicitly start it via the root-approved existing lifecycle. On the single VoiceLink task:

```cpp
auto wifi = voicelink::nativeWifiPort(30000);
if (!wifi) { /* report service not ready and return/retry later; no accepted request */ }
// Construct Controller only with a live *wifi and actual other ports.
// Keep this optional and the process-lifetime radio service alive longer than Controller.
```

Do not invoke Controller with an empty optional. Do not call k7wd_pump from the VoiceLink task: the existing shared service owns pumping and radio workers. Default construction with explicit references remains available for controlled tests; production should use the real getter factory. The image must link/export the same service instances to both callers; this has not been verified for independently loadable module/protected-process configurations. Root owns full NuttX compile/link and live initialization verification.

## Ownership / asynchronous semantics

- beginScan returns receipt only; snapshot ready comes through ws_voice_poll after real supervisor-authored STOP/CLOSE/worker/RX/offline fences. Cancel is idempotent request; held lease survives until cleanup, and BLE/voice cannot bypass it. Current filtered voice view skips invalid UTF8/ASCII control/hidden SSIDs without rewriting bytes or damaging the raw BLE snapshot. No new collector implementation.
- beginConnect passes caller bytes to k7wd_voice_begin, which copies them into bounded service credentials before return. Adapter holds no password copy or pointer. Controller wipes its input; queued cancellation wipes queue credentials immediately; pump clears dequeued/transient broker jobs. A running backend owns a separate copy until it can safely wipe after worker completion/join; cancellation cannot free a live borrow prematurely. The adapter cannot itself attest hardware backend cleanup or repair it.
- Owner-scoped service calls prevent BLE/voice cross-cancel; stale old-ID cancellation cannot cancel a new transaction. IDs remain service-wide monotonic, including normal rejected attempts; invalid service context/exhaustion can return0. Service history retention is bounded; no guarantee of perpetual old-result availability.
- IpReady requires held/authenticated/DHCP/worker-exit authoritative completion and valid IPv4 in the underlying broker plus adapter validation. PROGRESS never promotes success. Queue acceptance, scan completion, association and mock injected IP are not real connectivity evidence. The current broker does not distinguish WrongPassword/NetworkNotFound reason codes, so adapter retains generic Failed rather than inventing diagnoses. Error integers include internal enum-derived failures; do not format them as guaranteed POSIX errno without mapping.

## Host verification and limits

run_tests.py builds frozen formal C core, candidate C++ adapter and reused/extended tests with -Wall -Wextra -Werror. O0/O2, exceptions on/off each passed 4377 checks (100 concurrent scan arbitration rounds included). Separately current frozen formal core.cpp/parsers.cpp compiled at O0/O2 against the same headers. Each compile/executable bounded30s. Exact commands and raw output: test-output.txt.

Added checks: native factory unpublished/partial/invalid timeout and actual associated injected services; caller password mutation after begin does not alter queued copy; cancel-before-submit clears full credentials with no backend call; stale cancelled ID does not cancel next connect; queue/broker transient zeroing; backend test copy explicitly cleared; foreign BLE cancellation rejected. Existing tests cover async scan/connect cancellation, missing cleanup fences, late events, real core lease arbitration, mixed SSID views, error propagation and no IP success from incomplete facts. Hardware/clock/service getters are explicitly test doubles; real broker/dispatcher/collector/scan code is compiled. This is not firmware, ASR, TTS, radio or credential-erasure-on-real-device acceptance.

Authoring harness initially missed a declaration during CRLF transformation and briefly inserted a declaration into the extern-C block; compiler rejected both before any test execution. Corrected generation now uses one namespace declaration; final tests passed. No SDK failure was hidden or fixed by changing formal source.
