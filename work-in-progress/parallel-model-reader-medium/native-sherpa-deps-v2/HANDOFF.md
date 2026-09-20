# ASR offline dependency inputs, second stage

All five new archives downloaded from official URLs and matched their exact recipe SHA256 before saving: OpenFST sherpa-onnx-2024-06-13, KissFFT febd4caeed32e33ad8b2e0bb5ea77542c40f18ec, simple-sentencepiece0.7, cppjieba sherpa-onnx-2024-04-19, and Eigen3.4.0. See download-results.json for URL/size/hash and actual archive CMake snapshots. v1's three verified archives remain untouched. No TTS dependencies, native configure/build, model execution or SDK actions.

## Complete source-acquisition list for the reviewed ASR-only feature scope

Use source archives from v1: kaldi-native-fbank1.22.1, kaldi-decoder0.2.10, kaldifst1.7.16. Use v2: openfst.tar.gz, kissfft.zip, ssentencepiece.tar.gz, cppjieba.tar.gz, eigen.tar.gz. Together these cover the actual non-test/non-Python FetchContent chain inspected for sherpa's ASR core (ORT is supplied independently). Source snapshots in cmake-snapshots retain exact file hashes; this is acquisition closure for these settings, not successful NuttX configuration or build closure.

Set overrides after root safely extracts each VERIFIED archive into its separate stage:

| Variable | Verified tree |
|---|---|
| FETCHCONTENT_SOURCE_DIR_KALDI_NATIVE_FBANK | v1 fbank1.22.1 |
| FETCHCONTENT_SOURCE_DIR_KALDI_DECODER | v1 decoder0.2.10 |
| FETCHCONTENT_SOURCE_DIR_KALDIFST | v1 kaldifst1.7.16 |
| FETCHCONTENT_SOURCE_DIR_OPENFST | v2 OpenFST2024-06-13 |
| FETCHCONTENT_SOURCE_DIR_KISSFFT | v2 fixed KissFFTcommit |
| FETCHCONTENT_SOURCE_DIR_SIMPLE-SENTENCEPIECE | v2 simple-sentencepiece0.7 |
| FETCHCONTENT_SOURCE_DIR_CPPJIEBA | v2 cppjieba2024-04-19 |
| FETCHCONTENT_SOURCE_DIR_EIGEN | v2 Eigen3.4.0 |

The hyphen in SIMPLE-SENTENCEPIECE is intentional: the recipe's FetchContent name is simple-sentencepiece, while its build target is ssentencepiece_core. Do not use the target name for the override.

Keep KALDI_NATIVE_FBANK_BUILD_PYTHON/OFF, tests/OFF, KALDI_DECODER_BUILD_PYTHON/OFF, KALDI_DECODER_ENABLE_TESTS/OFF, KALDIFST_BUILD_PYTHON/OFF, SBPE_BUILD_PYTHON/OFF and SBPE_ENABLE_TESTS/OFF; top-level SHERPA_ONNX_ENABLE_TTS/PORTAUDIO/WEBSOCKET/SPEAKER_DIARIZATION/PYTHON/TESTS/BINARY OFF and BUILD_SHARED_LIBS OFF. The existing sherpa recipes set several nested options, but verify final cache values. No pybind11/gtest acquisition needed under those branches.

OpenFST's real top-level CMake optionally finds ICU and ZLIB. Set CMAKE_DISABLE_FIND_PACKAGE_ICU=TRUE and CMAKE_DISABLE_FIND_PACKAGE_ZLIB=TRUE for the initial scope if no reviewed target versions are provided; do not pick host libraries. Nested OpenFST recipe controls optional fst tool/library switches; retain fst/fstfar required by core. Do not enable binaries or Python accidentally. cppjieba's INTERFACE target points to include and bundled deps/limonp/include; no extra limonp download is needed. Test/legacy CMake modules are source archive content, not executable instructions to run.

## Reproducible Eigen isolation

Sherpa/kaldi-decoder's verified Eigen3.4.0 hash8586084f71f9bde545ee7fa6d00288b264a2b7ac3607b974e54d13e7162c1c72 now matches exactly. It is separate from ORT's post3.4 fixed Git tree. Configure sherpa in a separate CMake build/cache from ORT, set only its EIGEN override to this3.4.0 tree, and never add ORT private Eigen/core include directories to sherpa. Supply ORT's public session API headers and real target archive closure through a reviewed imported/interface target; bypass sherpa's runtime package downloader for NuttX only with that genuine target present.

Sherpa online-paraformer-model.h includes onnxruntime_cxx_api.h and exchanges Ort::Value objects. That header is an inline wrapper around onnxruntime_c_api.h; the runtime boundary uses opaque Ort handles and C API table functions, not Eigen::Tensor/Matrix types. Sherpa's own public C API similarly avoids Eigen types. This supports compile-time header isolation and avoids an across-boundary Eigen layout contract. It does NOT mathematically guarantee no same-name weak template symbols/ODR conflict after both static archives enter one firmware address space. Root must inspect final linked symbol origin and incompatible duplicate instantiations under its exact compiler/visibility options. Do not silently resolve this by replacing one version or claiming namespaces are isolated automatically.

## Remaining gates

Source inputs now present for the inspected ASR-only chain; target source selection/CMake compatibility and any generated headers remain unbuilt. Root must validate no offline fetch attempts, toolchain/ASM/C++ ABI, real ORT import closure and final dependency map. Static archive creation is not a firmware link. License notices from each archive must remain preserved. TTS cppinyin/espeak/piper acquisition remains deliberately outside this ASR-only task.

Reproduce fetch.py with an outer process deadline if required; each network request has25s socket timeout, elapsed90s budget checked per chunk,40MiB per archive cap. Script verifies hashes before any accepted archive write; no mirror endpoints. Large model files were not accessed.
