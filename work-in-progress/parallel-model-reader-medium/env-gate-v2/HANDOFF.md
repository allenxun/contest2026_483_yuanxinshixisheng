# ORT Env gate v2: real loading fallbacks and join ownership

Full source prerequisite verified: `work-in-progress/native-voice-sources/onnxruntime-extracted.json` exists and records commit8f5c79cb63f09ef1302e85081093a3fe4da1bc7d/archive3f92301fad8c5076b56f1e7f674d1d9860aea94a941ab1b6e73725762bf80f2a. Selected actual extracted call-site files plus v1 candidate are copied/hash-frozen in inputs.json. No source download or SDK/device/formal changes. Full ORT remains uncompiled.

## Evidence that v1 is not a permanent model-loading gate

| API/path | Actual source evidence and action |
|---|---|
| GetCanonicalPath | Whole .cc/.h search finds calls only in orttraining/core/framework/checkpointing.cc:256/260. CPU inference core has no call. Thus no need to invent a canonical string or implement realpath to unblock ordinary ONNX inference. Keep NOT_IMPLEMENTED with training disabled; it would genuinely block checkpoint training paths. |
| Main ONNX path | core/graph/model.cc:488–532 LoadModelHelper calls FileOpenRd, loader(fd), then FileClose. Model::Load(fd) at689–703 uses protobuf FileInputStream/ParseFromZeroCopyStream and GetErrno. This is a real fd read path, independent of Env.ReadFileIntoBuffer and mmap. Protobuf/ONNX libc dependencies still need native build validation. |
| External tensor data | core/framework/tensorprotoutils.cc:775–805 GetFileContent first MapFileIntoMemory. Any non-OK status reaches new char[length] and ReadFileIntoBuffer. Copy memory is paired with DeleteCharArray via OrtCallback. Keep mmap NOT_IMPLEMENTED; this genuine fallback can load data when ordinary read and heap allocation succeed. It may allocate the full tensor length, not just64KiB. |
| Other external read | tensorprotoutils.cc:184 calls ReadFileIntoBuffer directly. Bound/read failures propagate. v1's64KiB chunk cap bounds an I/O request, not total allocation. |
| Unsupported write/dlopen | Read-only CPU model path above does not require directory create/delete, write-open or dynamic plugins. Keep explicit unsupported responses; disabling such capabilities must also be reflected in build/features. This audit is not a proof no other optional EP or serializer calls them. |

Snapshot names input/1-model.cc, input/2-tensorprotoutils.cc, input/4-checkpointing.cc correspond to those paths. The previous caveat that canonical might block ordinary loading is now narrowed by these real call sites: it does not in the inspected CPU path. File content/path immutability across separate opens remains required; no same-handle hash guarantee is invented.

## Small v2 changes

- FileOpenRd validates actual opened fd with fstat and regular-file/nonnegative-size checks under ORT_K7_NUTTX. Rejection closes once, sets fd=-1, and returns SYSTEM error. Descriptor consumers cannot bypass regular-file validation merely because main ONNX loading uses protobuf instead of ReadFileIntoBuffer. Trusted mounted paths still required: this check is after open, not a general protection against malicious device/symlink namespaces.
- Preserve ordinary existing open/read/close. No NOT_IMPLEMENTED for FileOpenRd. Caution: upstream LoadModelHelper has special handling for SYSTEM errors but can reach loader(fd) after a non-SYSTEM open failure; do not later replace FileOpenRd with a NOT_IMPLEMENTED stub without fixing that caller. This patch avoids introducing such a path and does not broaden into an unrelated model.cc rewrite.
- Target pthread constructor diagnostics use the returned pthread error code, not unrelated errno. Existing v1 attr RAII remains. Target custom thread callbacks are rejected before creation: the void custom join API provides no checked result contract here. Default native pthread remains usable.
- Target destructor now checks pthread_join in release as well as debug. **A nonzero join result invokes std::terminate, never returns to free pool state.** This is an explicit fatal-invariant policy, not recoverable cancellation. Root must review NuttX termination scope before integration. It is preferable to silently freeing memory still reachable by an unjoined worker; adding recoverable held pools would require broader ownership/API changes and is outside this patch. No automatic thread cancellation or detach is added.

Why fatal rather than a normal error: include/onnxruntime/core/platform/EigenNonBlockingThreadPool.h:710–722 SignalAllAndWait resets each worker thread object; destructor at810–812 calls it. Worker callbacks were passed pool `this` at799. Returning after failed join permits later pool/queue destruction with potential live references. A destructor cannot report a normal Status upward. The existing void custom join path cannot be independently verified, hence the early target-only rejection. No deadline is added to blocking join; bounded shutdown is still unproven.

## Apply and verification limits

Use **either** full-env-gate.patch on the exact extracted base **or** v1-to-v2.patch on v1's env-gate.cc, not both. Keep v1 platform-gate.patch / ORT_K7_NUTTX CMake opt-in and off_t64/CPUINFO-off conditions. Non-target branches preserve original behavior. env-gate.cc is the full reviewed candidate for comparison. Complete ORT includes/dependencies and NuttX compile remain root work.

run_tests.py extracts the exact target checked-join body into a small C++17 harness. O0/O2 strict builds join a real host pthread successfully. A separate run injects EINVAL only after joining the real thread, installs a test terminate handler that exits77, and proves the post-join release marker is never reached. This is explicit failure injection, not a real OS join failure or board shutdown test. Source structure checks confirm actual mmap-failure copy branch and main model path with no canonical call. Exact commands/stdout in test-output.txt; compile30s/executable15s bounds. No fake full-ORT compilation or actual model run is claimed.

The new FileOpenRd branch has source review, not compiled ORT/target tests. Remaining dependencies include actual protobuf reads, native allocator capacity and callback frees, error propagation on scoped-close failure, C++ unwind, other Env platform files, and exact target termination behavior. These are explicit next gates, not fallback-to-host inference proposals.
