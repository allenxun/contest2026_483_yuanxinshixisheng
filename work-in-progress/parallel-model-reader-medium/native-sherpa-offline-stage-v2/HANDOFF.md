# Correction: real Sherpa module resolution and Eigen math gate

## Corrected dependency selection

The prior v1/v2 dependency notes described nested recipe files as the actual combined-build contract. That conclusion was incomplete and is corrected here. Their archives remain authentic to their own hashes, but **they are not the versions selected by the actual Sherpa configuration**.

Fixed sherpa CMakeLists.txt:353–354 appends its own cmake directories. kaldi-decoder CMakeLists:41 appends ${CMAKE_SOURCE_DIR}/cmake, and kaldifst:73–74 appends ${CMAKE_SOURCE_DIR}/cmake/Modules and /cmake. In a combined Sherpa configure CMAKE_SOURCE_DIR is still the top-level Sherpa source. Consequently include(kaldifst)/include(openfst) resolves the top-level helper, not the local nested file previously inspected. Actual evidence/native-sherpa-asr-config1-20260911/configure.log confirms calls to1.7.17 and2024-06-19 while old override directories held1.7.16 and06-13. That mixed provenance must not be retained silently.

This directory downloads from the actual selected official helper URLs and verifies their recipe SHA256:
- kaldifst1.7.17: c4b701a23a400bda8032586b02c7e0d5e813a765832df60c23e6df9e62b010f4.
- OpenFST sherpa-onnx-2024-06-19: 5c98e82cc509c5618502dde4860b8ea04d843850ed57e6d6b590b644b268853d.

Both VERIFIED in download-results.json. Replace only corresponding source overrides with separately extracted matching archives in a NEW root stage/build; never overwrite frozen v1 sources. Retain the other six verified sources. The top-level Eigen helper also selects3.4.0 with the same hash already acquired. To establish configuration provenance, record include trace/module path and each override tree/hash as well as printed recipe URL. A recipe URL alone does not establish the actual source when source overrides are in use.

## Eigen math failure: facts versus unresolved cause

Eigen3.4.0 CMakeLists:89 appends -std=c++03 if EIGEN_TEST_CXX11 is false and its compiler flag test passes. config1 log says that flag probe succeeded. This can affect a libc++ toolchain that expects a newer standard. FindStandardMathLibrary.cmake:24–30 compiles a <cmath> main calling std::sin/std::log. :33–34 explicitly resets CMAKE_REQUIRED_FLAGS and CMAKE_REQUIRED_LIBRARIES; :52 sets the second probe's library to bare m. Thus merely setting an outer CMAKE_REQUIRED_LIBRARIES=<absolute libm> will be overwritten.

Actual configure.log only says both probes failed; it does not include compile/link diagnostic details. CMakeCache records failed booleans but cannot distinguish missing <cmath>, C++ standard mismatch, missing bare -lm search path, startup/linker-script problems or a target link failure. The failed try_compile output (CMakeError.log/CMakeConfigureLog.yaml) is needed before assigning a root cause. Presence of real libm elsewhere does not fix an unrelated compile failure.

Minimal next procedure (not executed here): capture the exact failed source/command/output; use a new configure cache to avoid stale failed tests. Set EIGEN_TEST_CXX11=ON to avoid the legacy03 branch if the target libc++ accepts11, or scope a NuttX condition retaining the actual17 standard if it requires17. Do not call a compiler-only flag test proof that standard headers compile. Do not FORCE STANDARD_MATH_LIBRARY_FOUND or either result to true.

For a real math-link gate, a narrowly scoped NuttX FindStandardMathLibrary path must accept the **absolute target libm archive plus actual libc/libgcc/startup/linker options supplied by root**, preserve those in CMAKE_REQUIRED_LIBRARIES instead of replacing with bare m, and use CMAKE_TRY_COMPILE_TARGET_TYPE=EXECUTABLE only for that test. CheckCXXSourceCompiles then really links but does not run the target. Its required C++ standard and toolchain flags must match the target. Restore caller settings afterward and assign FOUND only from the actual check result. If startup/linker context is unavailable, report the link gate incomplete instead of returning success. With STATIC_LIBRARY try_compile, successful ar creation never proves sin/log resolution; adding libm to that static probe cannot convert it into link evidence.

No guessed executable-link setup is supplied because the root owns real SDK runtime/linker inputs and the failing diagnostic is not yet frozen here. This is an explicit remaining gap, not a dummy library or declaration workaround. Current delivery corrects source input acquisition and gives exact required math-probe changes without claiming the cause or a passed target link.

No SDK/device/formal changes, no configuration or build performed; only official archive downloads and read-only frozen-input review. Prior results preserved.
