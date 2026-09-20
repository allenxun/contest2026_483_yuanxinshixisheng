# Config2 driver candidate

This is a parent-run Linux host driver, not an SDK run or successful configuration report. No SSH transport, credentials, target execution or build is included. Transfer this directory with the two v3 source trees; preserve source modes from v3 source-manifest.json. Do not execute config1-reference.py.txt.

Retained: original stage/sherpa with the reviewed real ORT import patch, the six v1 dependencies under stage/sources, the exact config1 ORT compile-attempt6 success prerequisite, sorted real *.a archive discovery under ORT/build, actual public headers, session-toolchain.cmake and MinSizeRel. Archive bytes and toolchain hash are recorded when executing. This preserves config1's archive selection; archive magic and compile success do not prove final dependency/link closure.

Changed: both build and output must not exist. Explicit command-line FetchContent overrides AFTER the old initial cache select v3 kaldifst 1.7.17 and OpenFST sherpa-onnx-2024-06-19. The final cache sets EIGEN_TEST_CXX11=ON without FORCE. No math probe results are preseeded; parent C++17 is untouched. Existing six source trees and corrected two are verified against frozen manifests, including membership, before invocation. Modified upstream sources must be reviewed and explicitly re-frozen, not silently accepted.

Parent reproduction (replace the candidate/v3 transfer paths with actual read-only staging paths):

```sh
cd /home/swl/openvela
source build/envsetup.sh
python3 /dev/shm/config2-candidate/configure_config2.py \
  --stage /dev/shm/velavision-sherpa-asr-20260911 \
  --corrected /dev/shm/sherpa-v3/sources \
  --ort /dev/shm/velavision-ort-session-20260911 \
  --build /dev/shm/velavision-sherpa-asr-20260911/build-config2 \
  --output /dev/shm/velavision-sherpa-asr-20260911/config-attempt2 \
  --cmake /dev/shm/cmake-3.28.3-linux-x86_64/bin/cmake \
  --ninja /home/swl/openvela/prebuilts/build-tools/linux-x86_64/bin/ninja
```

Without --execute, this only reads/validates inputs and prints the exact command. Repeat with --execute for parent-authorized configuration. The direct CMake process timeout is 240 seconds; this does not promise recursive process-group termination of arbitrary descendants. Capture configure.log/result.json and build-config2/CMakeFiles/CMakeConfigureLog.yaml plus CMakeCache.txt. Check new math probe compile flags use C++11 rather than C++03; check later Sherpa flags remain17. STATIC_LIBRARY try_compile still does not establish math symbol resolution: final native linkage must use real libm.

Actual local tests: all 2080 retained source files and 763 corrected source files verified, command ordering/no math overrides, existing build/output rejection, changed-source rejection. Five checks passed. Initial test assertion used POSIX literal separators under Windows and failed; corrected expectations use pathlib strings, with no driver behavior change. No CMake or SSH process was run. prepare_test.py reproduces these local checks (writes only this candidate directory).

The driver reuses the parent's already staged Sherpa/import patch; it does not apply or silently replace that source. Its present patch/version provenance remains the parent's config1 staging evidence, while dependency snapshots and the original reference driver are hashed in inputs.json. Config2 compile/configure outcome remains untested here.
