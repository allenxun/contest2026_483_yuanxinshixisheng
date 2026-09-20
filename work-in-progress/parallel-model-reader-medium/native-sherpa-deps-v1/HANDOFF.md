# Verified minimal sherpa ASR dependency acquisition

Three official archives downloaded and SHA256 verified before saving/reading: kaldi-native-fbank1.22.1, kaldi-decoder0.2.10, and its actual nested kaldifst1.7.16. download-results.json and nested-download-results.json include URL, bytes, expected/actual SHA256 and CMake snapshot hashes. Only official GitHub URLs used; mirror URLs remain quoted source metadata and were not requested. No sources built/executed, no SDK/device/formal changes. Archives stay here for root to extract to a NEW staging directory; only CMake source files were expanded for review.

An initial fbank URL mistakenly used the k2-fsa organization and returned404. initial-attempt.json preserves it. The corrected fetch.py uses the exact sherpa recipe csukuangfj/kaldi-native-fbank URL and verified the pinned digest; no checksum changed. Each request25s socket timeout,90s elapsed budget checked between bounded1MiB reads,32MiB archive limit. This is not a hard process-wide timeout if an underlying call stalls beyond its socket guarantee; root can apply an outer subprocess timeout when rerunning. No rejected bytes were saved as accepted source.

## Actual nested chain (read from verified archives)

sherpa recipe -> kaldi-native-fbank1.22.1 SHA256 b292ddd1fa121f28371d11c14dd016c59c54b3f0dbb2bb2cfdc82d562564d0f5 -> CMakeLists.txt:136 include(kissfft). Its actual cmake/kissfft.cmake pins https://github.com/mborgerding/kissfft/archive/febd4caeed32e33ad8b2e0bb5ea77542c40f18ec.zip SHA256497103e664168ebe39580b757adbe616f6cf85a16572af581ca7bc42d0ab13fd. KissFFT is identified but NOT downloaded in this minimal delivery.

sherpa recipe -> kaldi-decoder0.2.10 SHA256 a3d602edc1f422acfe663153faf3f0a716305ec1f95b8fcf9d28d301d6827309 -> CMakeLists.txt:71 include(kaldifst),:72 include(eigen). Its own kaldifst recipe pins **1.7.16**, SHA256 f338135a3d137b7a8c287e2ca2e0918e1394e1c08bad53b26e7be03a5d4a1066. This differs from sherpa's separate1.7.17 helper and is the actual nested source contract. kaldi-decoder-core publicly links kaldifst_core.

Verified kaldifst1.7.16 cmake/openfst.cmake:6–8 pins https://github.com/csukuangfj/openfst/archive/refs/tags/sherpa-onnx-2024-06-13.tar.gz SHA256 f10a71c6b64d89eabdc316d372b956c30c825c7c298e2f20c780320e8181ffb6. OpenFST identified but NOT downloaded. Do not substitute the different top-level sherpa helper hash. Target fst/fstfar must come from this reviewed nested recipe unless an explicit source-override compatibility decision is recorded.

Decoder Eigen recipe pins3.4.0 tar.gz SHA2568586084f71f9bde545ee7fa6d00288b264a2b7ac3607b974e54d13e7162c1c72, different from ORT's already verified post3.4 commit tree. Both use FetchContent name eigen. In a combined graph, first-declaration/population behavior matters; root must choose/document a compatible single source or isolate builds/includes. Existing ORT Eigen tree does NOT pass decoder's old archive lock by implication. No new Eigen download or lock change here.

## Offline integration

Extract each VERIFIED archive into a new root-owned stage with path/symlink validation and preserve input hashes. Set FETCHCONTENT_SOURCE_DIR_KALDI_NATIVE_FBANK, FETCHCONTENT_SOURCE_DIR_KALDI_DECODER and FETCHCONTENT_SOURCE_DIR_KALDIFST to the respective inner source roots. Once separately acquired/verified, nested overrides are FETCHCONTENT_SOURCE_DIR_KISSFFT, FETCHCONTENT_SOURCE_DIR_OPENFST, and FETCHCONTENT_SOURCE_DIR_EIGEN. Use real target toolchain and disabled tests/Python; do not enable nested pybind11/gtest downloads. FetchContent recipe metadata is in recursive-recipes.json. Disconnected mode alone does not provide or verify missing sources.

Remaining ASR acquisition: KissFFT and actual nested OpenFST sources, Eigen override decision, plus sherpa's unconditionally configured simple-sentencepiece/cppjieba from previous map. Inspect newly fetched dependency CMake before claiming recursive closure. TTS/espeak/piper/cppinyin are intentionally not fetched. No native library compilation, runtime or full ASR readiness claim.
