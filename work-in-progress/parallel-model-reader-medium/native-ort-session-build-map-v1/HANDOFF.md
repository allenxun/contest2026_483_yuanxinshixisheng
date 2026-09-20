# From common objects to a real CPU Session

Scope: frozen ORT1.17.1, a tiny ONNX opset13 Add graph (two FLOAT[4] inputs, one FLOAT[4] output, no weights/external data). This is a Session/allocator/parser/kernel gate, not a Paraformer/TTS operator set. No source download/build/model generation/inference performed here.

## Required upstream targets

cmake/onnxruntime.cmake:178–208 records the reverse dependency order: onnxruntime_session, optimizer, providers, framework, graph, util, MLAS, common, flatbuffers (plus enabled optional providers/features). Use these real upstream targets; session.cmake:32 creates only a static archive and does not by itself link a runnable Session. CPU registrations and kernels live in onnxruntime_providers, selected by onnxruntime_providers_cpu.cmake; MLAS is separately onnxruntime_mlas (mlas.cmake:13,58). Even a one-Add registration does not automatically remove all provider source compilation, schemas, runtime or optimizer references. Full link determines the actual closure.

Next build sequence: generated ONNX protobuf + target protobuf runtime; onnx/onnx_proto and FlatBuffers; graph/util/MLAS; framework; optimizer/CPU providers; session; finally a NuttX application with real OrtGetApiBase C API references and these archives plus current static dependency closure. Preserve upstream link order/transitive dependencies and resolve every required symbol. Keep CPUInfo disabled unless its actual platform is ported, but do not disable true ARM64 architecture macros. MLAS selects ARM64 ASM at mlas.cmake:270–311; the toolchain must support real ASM/preprocessor options and these objects require independent compilation, not reuse llama/ggml objects.

## Missing acquisition and generators

`dependency-lock-map.json` extracts exact official ORT deps.txt versions/URLs/SHA1 and whether the normal local deps/<name>.zip exists at audit time. False means absent at that location, not an exhaustive disk search. Eigen has the separate already-verified commit/tree override. New core dependencies beyond present common support include ONNX1.15.0, protobuf21.12, FlatBuffers1.12.0, Boost mp11 and re2; json is used by graph/session as well as profiling. No new acquisition is authorized/executed by this deliverable.

1. Obtain verified source trees using the fixed locks in a later acquisition task; build target protobuf-lite (default USE_FULL_PROTOBUF OFF), ONNX and associated generated sources. A host protoc21.12 executable is a build tool, not an ARM64 library: set ONNX_CUSTOM_PROTOC_EXECUTABLE to its real host path. protobuf_function.cmake:40–44 otherwise tries the built protoc target; do not execute target protoc on the host.
2. Use ONNX's actual generator to produce onnx .pb.h/.pb.cc with namespace/options matching ORT. graph.cmake:91 explicitly depends on onnx_proto and FlatBuffers; external_deps.cmake:500 notes generated ONNX source ordering. Empty replacement generated headers are invalid.
3. ORT includes checked-in flatbuffer schema/generated assets; use its pinned FlatBuffers headers and existing onnxruntime_flatbuffers target. flatbuffers.cmake:20–23 only adds flatc dependency when FLATBUFFERS_BUILD_FLATC is enabled. Do not blindly run target flatc; any regeneration needs the matching host tool and an explicit output diff/hash.
4. Regenerate onnxruntime_config.h from the real template with actual feature measurements; reuse Env/logging/Abseil reviewed NuttX patches in the new full source stage. Existing21 common objects are evidence, but reuse requires identical headers/ABI/flags to the newly configured graph.

## Narrow Add registration candidate

`session-initial-cache.cmake` is an initial-cache fragment for upstream ORT CMake, not a complete NuttX port. It keeps MINIMAL_BUILD OFF because that option explicitly drops ONNX format support (CMakeLists:156); exceptions stay on, shared/Python/training/non-CPU extras off. `add-only.config` selects ai.onnx;13;Add without type reduction. Before configuration, generate upstream reduction files in the SAME new build directory:

```sh
python <ORT>/tools/ci_build/reduce_op_kernels.py <candidate>/add-only.config \
  --cmake_build_dir <new-build> --is_extended_minimal_build_or_higher
```

This invocation is based on reduce_op_kernels.py:320–346; it has not been run here. Full-build flag is appropriate because full ONNX is higher than extended minimal. providers.cmake:6–44 consumes op_reduction.generated replacements; setting REDUCED_OPS_BUILD alone without generation is incomplete. Do not turn on --enable_type_reduction until a matching generated type configuration is available.

Then root can configure the upstream <ORT>/cmake with its real NuttX toolchain, -C session-initial-cache.cmake, ONNX_CUSTOM_PROTOC_EXECUTABLE and verified FetchContent source overrides. Every required dependency must be available offline first; do not let this candidate silently fetch mismatched or Linux binaries. Full upstream CMake NuttX platform support, dependency discovery and target flags remain necessary differences; the initial cache does not claim to solve them.

## Actual acceptance and model scope

Use a host generator solely to create/validate the tiny deterministic Add ONNX artifact and record its generator/model hash; runtime inference remains on the board. C API application sets intra/inter-op1, sequential execution, graph optimization disabled, real CPU provider/default, then CreateSession from ordinary trusted model file (or bytes for a first parser-only test), allocates two real input tensors [1,2,3,4] and [10,20,30,40], calls Run and verifies [11,22,33,44]. Release outputs/inputs/session/options/env on all failure paths. A bytes-model test does not validate ordinary-file I/O; add a separate same-artifact file Session test. No fabricated success or host inference counts as target acceptance.

This Add-only config cannot load actual Paraformer or VITS graphs: those need an inventory of all model opsets/operators/types, generated full matching registrations, memory planning and streaming/audio integration. Disabling graph optimization for Add avoids optimizer-introduced fused operators in this gate but does not prove optimizers can be removed from the archive closure. Existing1GiB arena is not automatically used by ORT allocations. Thread join fatal policy, full allocator failure behavior and file/external-data paths remain previously documented gates.

Deliverable verification: fixed file hashes, upstream target/code-location audit, exact lock extraction. No complete CMake configure, target link or inference success asserted.
