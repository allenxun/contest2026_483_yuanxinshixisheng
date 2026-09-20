# Native static dependency CMake candidate

Entry: CMakeLists.txt; exact21 ORT1.17.1 ABSEIL_LIBS roots: ort-abseil-targets.cmake. These are real upstream absl:: targets, plus nsync_cpp. k7_native_deps builds the target dependency graph; k7_ort_static_deps is an INTERFACE target for downstream linking. No fake executable, synthetic pthread library, Linux macro, network fetch, install, or merged archive.

Root supplies real NuttX ARM64 toolchain and verified source paths in an independent build directory:

```sh
cmake -S /path/to/native-static-deps-cmake-v1 -B /path/to/new-build \
  -DCMAKE_TOOLCHAIN_FILE=/path/to/actual-nuttx-toolchain.cmake \
  -DK7_ABSEIL_SOURCE=/path/to/verified/abseil_cpp \
  -DK7_NSYNC_SOURCE=/path/to/verified/google_nsync
cmake --build /path/to/new-build --target k7_native_deps --parallel 2
```

Toolchain must set CMAKE_SYSTEM_NAME=NuttX and CMAKE_SYSTEM_PROCESSOR=aarch64 (or arm64), real compiler/sysroot/includes/ABI, and required target runtime link context. Do not label a host compiler NuttX. Existing read-only source inputs: private/native-ort-env-stage/abseil_cpp and google_nsync. Input SHA256 files recorded; source archives/provenance remain root's verified dependency staging.

Nsync's real CMake uses its generic C++11 mutex/condition-variable implementation for NuttX and copies shared internal .c sources to compile them as C++. It requests source-level -std=c++11; this upstream behavior is retained, while Abseil uses C++17 and its propagated standard requirement. Keep exception/runtime ABI compatible. nsync C target exists upstream but EXCLUDE_FROM_ALL and explicit cpp build roots avoid building unrelated tests/C archive. Abseil source graph includes header-only targets; the prior97 declared targets are not97 required archives. The upstream targets resolve selected-platform transitivity.

FindThreads is intentionally not forced to success. If toolchain uses CMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY, a Threads probe may prove compile availability without proving pthread link symbols. Record that limit and perform actual final NuttX ELF linking against its real scheduler/libc/libc++ later. Never satisfy detection by creating an empty libpthread or asserting libc pthread support without evidence. No -pthread flag is injected by this entry; upstream/toolchain detection owns platform options. Likewise CMake availability/version and upstream platform support are genuine configure gates, not already passed here.

When integrating a downstream link in the same CMake graph, use target_link_libraries(actual_target PRIVATE k7_ort_static_deps) along with common and other required targets; do not drop transitive dependencies or assume static .a creation checks unresolved references. Standalone output archives need their full target dependency/order information carried into final linking. This candidate deliberately does not claim full common/runtime closure, target execution, or ASR deployment.

Actual verification here: read-only extraction/assertion of21 exact upstream root targets and source hashes. No target configure, compiler tests, SDK operation, or host mock build performed. Parent has actual21 common objects; this is the next separate dependency build gate.
