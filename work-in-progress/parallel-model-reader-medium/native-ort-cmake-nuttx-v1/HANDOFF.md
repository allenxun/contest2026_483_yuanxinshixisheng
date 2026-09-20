# Minimal full-ORT NuttX CMake candidate

Apply candidate.patch only to a new fixed ORT1.17.1 source stage. Candidate copies of the three changed CMake files are under candidate/. No source/SDK build performed. Initial-cache.cmake preserves the Add-only full-ONNX choices of the previous delivery and disables shared/tests/benchmarks/extensions/training/XNNPACK/mimalloc/telemetry/syslog. It is not a complete toolchain.

Changes: CMakeLists target setup explicitly supplies PLATFORM_POSIX for CMAKE_SYSTEM_NAME=NuttX even if CMake does not set UNIX, plus ORT_K7_NUTTX to all ORT targets using this helper. external_deps turns CPUINFO_SUPPORTED off before clog/cpuinfo acquisition and rejects XNNPACK for this narrow port; it also disables target flatc generation for NuttX. MLAS ARM64 refuses missing CMAKE_ASM_COMPILER rather than silently selecting a host compiler, then uses upstream enable_language(ASM) unchanged. Other platforms retain previous branches. CPUINFO_SUPPORTED must remain absent from externally supplied flags as well; the patch cannot remove a user-injected -DCPUINFO_SUPPORTED.

Root toolchain must explicitly select real CMAKE_SYSTEM_NAME=NuttX, CMAKE_SYSTEM_PROCESSOR=aarch64, C/C++/ASM target compilers and identical target ABI/header/config options. ASM should use the actual target compiler driver appropriate to .S preprocessing; do not set host /usr/bin/cc or invent success variables. Keep Threads and target libm/libgcc/runtime handling real. No fake Threads_FOUND, missing-library stand-ins, Linux macro or mmap capability claim is introduced.

## Source overrides and patch preparation

`fetchcontent-map.json` contains exact declaration names, line numbers, blocks and PATCH_COMMAND assignment lines from fixed external CMake files. Use uppercase declaration names for CMake's FETCHCONTENT_SOURCE_DIR_<NAME> cache variable, NOT the deps.txt download alias:

- abseil_cpp -> FETCHCONTENT_SOURCE_DIR_ABSEIL_CPP
- google_nsync -> FETCHCONTENT_SOURCE_DIR_GOOGLE_NSYNC
- eigen, re2, flatbuffers, utf8_range, Protobuf, date, mp11, onnx, safeint -> corresponding uppercase suffix
- GSL -> FETCHCONTENT_SOURCE_DIR_GSL (not MICROSOFT_GSL)
- nlohmann_json -> FETCHCONTENT_SOURCE_DIR_NLOHMANN_JSON (not JSON)
- dlpack/cxxopts are also declared by upstream; supply them if configured scope populates them. Disabled optional providers/test dependencies remain in the inventory but are not a requirement to download them.

All overrides must point to verified, independently staged trees; source overrides skip normal population download/update/patch steps. Therefore explicitly apply each applicable upstream dependency patch BEFORE configuration, recording patch hash and before/after source hashes:

1. FlatBuffers: cmake/patches/flatbuffers/flatbuffers.patch (external_deps:95–106, normally Patch_FOUND).
2. Protobuf: cmake/patches/protobuf/protobuf_cmake.patch (:160–182, normally Patch_FOUND).
3. ONNX: cmake/patches/onnx/onnx.patch (:444–454, normally Patch_FOUND).
4. Abseil absl_windows.patch is conditional WIN32: not applicable to NuttX, even on a Windows host. Apply separately reviewed NuttX elf_mem_image.h patch instead, as already done by root.
5. GSL1064.patch only applies with CUDA; not applicable here. composable_kernel/Fix_Clang_Build.patch and xnnpack/AddEmscriptenAndIosSupport.patch belong to disabled optional providers. No nsync patch command is declared in this scope.

The normal upstream syntax is patch --binary --ignore-whitespace -p1 with the listed file on stdin, run in the dependency tree root. Root should first dry-run/check the exact patch against its tree; do not apply twice if staging already contains it. The presence of Patch_FOUND=false must not silently excuse losing a semantically required pinned-source modification. Full patch files are hashed in inputs.json; all active assignments are in the map. Existing Env v2/logging changes are additional ORT source patches, independent of these external dependency patches.

## Configure procedure and limits

First generate Add-only op_reduction.generated in the chosen build directory using the previous reduce_op_kernels command. Supply the verified host protoc21.12 via ONNX_CUSTOM_PROTOC_EXECUTABLE; never execute target protoc. Configure upstream cmake with actual toolchain, -C initial-cache.cmake, each verified source override, and host protoc path. The cache disables automatic package preference and sets FETCHCONTENT_FULLY_DISCONNECTED: it does not validate preexisting source paths/hashes, which root must check, and a missing tree should be treated as an actual blocker. Do not let a system-installed host ONNX/Protobuf substitute silently.

Review generated cache/compile_commands: NuttX/ARM64 selected, ORT_K7_NUTTX+PLATFORM_POSIX present on ORT units, CPUINFO_SUPPORTED absent, real ASM driver, CPU provider/reduced registration, target configuration consistent across libc/common/dependencies. The existing MIT strptime declaration-only compile override is not proof target libc has its implementation; keep root's real libc link requirement. Static dependency archives should remain normal demand-linked (not blanket whole-archive).

Native configure may expose more platform/feature assumptions; this small patch does not guarantee full configuration. No compiler detection result or target link outcome is forged. User-facing ASR/TTS readiness remains outside this build preparation.
