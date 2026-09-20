# ORT 1.17.1 NuttX Env gate candidate

**Two distinct deliverables:** (1) reviewed-source conditional Env/CMake patches, NOT compiled against full ORT; (2) a small real C file/time/pthread primitive probe, compiled and executed on Windows at O0/O2. No target compile/run, inference, SDK modification, device access or large source/model download. Never report the primitive probe as an ORT compile or model gate pass.

## Fixed interface evidence

inputs.json pins the prior official ORT1.17.1 posix/env.cc and common CMake, archived current project NuttX unistd/stat headers, formal radio pthread/time call sites, and model_reader source. Limited official single-file downloads obtained [pthread.h](https://github.com/open-vela/nuttx/blob/e987a81c32cab008d1a8521669e5488d00271322/include/pthread.h) and [time.h](https://github.com/open-vela/nuttx/blob/e987a81c32cab008d1a8521669e5488d00271322/include/time.h) at the recorded project SDK base commit, with hashes; these are header evidence, not current generated config verification.

- pthread header471/475/513/552/587: attr init/destroy/stacksize/create/join. Affinity615/618 is conditional and can return ENOSYS, so existence of the API is insufficient for an affinity claim.
- time header76/194/241: monotonic clock, clock_gettime, nanosleep; archived unistd383/389–392: close/lseek/read/pread; stat97/183: S_ISREG/fstat. Formal radio already calls create/join with explicit stack and monotonic clock, but its success cannot certify ORT thread pool behavior.

## Patch behavior

Apply env-gate.patch and platform-gate.patch to exactly the frozen ORT1.17.1 sources in an isolated future build. `CMAKE_SYSTEM_NAME=NuttX` opts on `ORT_K7_NUTTX` for onnxruntime_common; do not pretend the toolchain is Linux. Keep onnxruntime_ENABLE_CPUINFO=OFF and initial CPU/full-ONNX/exceptions settings from the previous source plan. This minimal conditional gate reuses POSIX Env's ordinary syscall code; a separately named NuttX Env source is optional later, not invented as available now.

With flag absent, original platform behavior remains selected. With flag present:

- Excludes sys/syscall, CPUINFO and Linux affinity code. Default parallelism1 is a conservative policy, **not physical core detection**. Explicit nonempty affinity requests fail before thread creation rather than being ignored; custom create requires its matching join callback.
- Retains real pthread creation/join, adds target-only attribute destruction on constructor exit. Does not fake successful creation or join. Existing upstream destructor release-build join-error handling remains an unresolved lifecycle issue (see below).
- Real nanosleep resumes EINTR; other errors throw, instead of silently returning from the void sleep interface. No busy-loop fake time.
- File length requires regular type; read verifies offset/length within fstat size, uses64KiB chunks, preserves short-read/EINTR/EOF failures. Compile-time off_t>=64-bit requirement rejects unsupported configuration. This does not ensure immutable content across reopen or size-preserving edits.
- mmap/unmap helpers, nftw deletion and dynamic-link headers/calls are excluded. MapFileIntoMemory, directory creation/deletion, write-open, canonical-path allocation and dynamic load/unload/symbol operations return NOT_IMPLEMENTED; write-open sets fd=-1 and dynamic outputs null. No operation returns pretend success. Existing output owners are not silently freed on unsupported map/canonicalization.

This is an early **capability gate**, not a fully working model Env. Callers that require canonicalization/mmap will fail until a genuine fallback or implementation is reviewed. No legacy fopen/model loader paths are redirected into model_reader by this patch.

## Actual small probe

`probe.c` exports `int k7env_gate_probe(const char *path)`; caller must serialize it and supply an owned immutable ordinary file containing exactly ABCD. It calls the frozen formal model_reader for expected length4, seeks1, reads BC, checks close, performs monotonic clock/nanosleep, then creates and joins one real pthread with64KiB stack and checks worker output. No mapping, dynamic loader, devices, model load or inference. Production code does not create its input file. `K7ENV_PROBE_MAIN` builds an optional CLI harness; target application registration is intentionally left to root.

Windows tests use the reader's explicit Win32 ordinary-file/_lseeki64 implementation and MinGW pthread/time APIs. They do **not** validate NuttX off_t or NuttX libc. O0/O2 -std=c11 -Wall -Wextra -Werror tests each passed the four-byte file and rejected short/missing file with held=0. Input generation is test-only in this new directory; exact commands/raw stdout in test-output.txt. run_tests.py bounds compiles30s and processes15s. No fake OS APIs used. Other error injections/allocator tests are not covered this round.

The probe has process-lifetime thread argument storage. If join fails, it retains held state and rejects reuse; target caller must not unload its code/storage. Join itself has no hard deadline here. Host process timeout can stop a test process, not establish a board cancellation guarantee. A worker stack size accepted on Windows is not proof it meets NuttX generated STACK_MIN.

## Remaining blocking checks before native model run

1. Obtain the complete locked ORT dependency tree; these patches have not been type-checked with ORT Status, Env, Eigen, GSL/Abseil etc. Full common target may expose additional platform files (`env_time`, telemetry, logging, filesystem helpers) requiring NuttX branches. CMake toolchain/MLAS assembly/link closure remains separate.
2. Match target C++ exception/unwind/stdlib policy. Existing PosixThread error messages use errno after some pthread errors, and its release destructor ignores join return; this candidate does not claim that lifecycle safe. Resolve before worker use, or initially verify the runtime creates no worker under explicit one-thread/sequential options. Do not infer that solely from requested num_threads.
3. Verify clock APIs, actual off_t/FS_LARGEFILE, heap alignment/allocator pairing and stack config using root's target build. 1GiB model arena is not an ORT allocator. Probe currently covers no custom allocator.
4. Trusted immutable regular model namespace and real loader fallback required: Env opens by path and scoped close logs cannot fully propagate every cleanup error. FileOpenRd/path-size checks do not prevent symlink/device namespace opening by themselves; only use supervisor-owned ordinary paths until reader integration is complete. No model inputs are opened by this audit.
5. Unsupported operations must remain failure until implemented; test real caller behavior rather than fabricating mapped pointers or canonical names. Then compile/link common, native C API micrograph, and only then actual ASR/TTS as separately planned.

No default success stubs, Linux artifact substitution or claims of full ORT/NuttX compatibility are supplied.
