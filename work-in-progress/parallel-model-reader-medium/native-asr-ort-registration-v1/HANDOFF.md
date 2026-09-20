# Add gate to ASR registration plan

The current Add-only archive is NOT ASR ready. The frozen conversion reports use ORT1.17.1 CPU with ORT_DISABLE_ALL and explicitly report no numerical comparison or board inference. This review hashes the actual encoder.ort and decoder.ort files against those reports, without loading or running them. The copied asr-required.config lists the serialized models' required kernel-version groups (10,11,13,14), not simply their source ONNX model opset14. Preserve every row/version; do not collapse to ai.onnx;14.

Minimal parent action: use a new build directory and run the SAME upstream generator with asr-required.config replacing add-only.config:

```sh
python3 "$ORT/tools/ci_build/reduce_op_kernels.py" "$ASR_CONFIG" \
  --cmake_build_dir "$NEW_ASR_BUILD" --is_extended_minimal_build_or_higher
```

Keep type reduction disabled (do not pass --enable_type_reduction). Keep CUDA disabled. Then run the existing successful CMake command against NEW_ASR_BUILD using its CURRENT working toolchain and all reviewed patches/dependency overrides. configure_native_ort_session9.py:64–66 establishes the old generator call, but its toolchain construction is historical: do not restore its old -mcpu flags over the later working -march/-mtune correction.

CMake boolean changes required: NONE. Retain onnxruntime_REDUCED_OPS_BUILD=ON, MINIMAL_BUILD=OFF, exceptions enabled, static CPU-only, tests/training/extensions/GPU disabled, current real NuttX Env/logging/Abseil adaptations and actual libm/iconv dependencies. Only config input and generated registration set/build identity change. Do not opportunistically switch to minimal-build solely because the artifacts are .ort; that changes the previously compiled feature surface.

Generated files: cmake/onnxruntime_providers.cmake:9–44 substitutes sources under $NEW_ASR_BUILD/op_reduction.generated, particularly onnxruntime/core/providers/cpu/cpu_execution_provider.cc, onnxruntime/contrib_ops/cpu/cpu_contrib_kernels.cc, and onnxruntime/core/providers/op_kernel_type_control_overrides.inc as present in target source lists. reduce_op_kernels.py:298–310 parses the new config, adds supported extended-minimal-or-higher required kernels and writes registration/type-control files. It deletes an existing generated directory; therefore use a new build. Hash ALL emitted files and retain generator stdout and compile commands proving the substituted files were compiled. This review does not claim generated output has already been produced or checked.

Rebuild the real upstream targets/archive closure in the new tree, especially onnxruntime_providers, and relink Session/ASR against this new set. Do not mix Add-only providers with the new Session archive or label the old whole library directory ASR-ready. Other targets may be byte-identical but should be resolved from the new audited build output. Generated registration now roots Conv, MatMul/MatMulInteger, DynamicQuantizeLinear, tensor transforms/reductions and the remaining listed kernels. Full strong-symbol closure and actual Session model loading remain separate gates.

StringNormalizer is absent from every config row. Thus these two converted ASR models do not require its registration. This does NOT remove string_normalizer.cc from upstream's source glob or its unconditional CMake Iconv discovery: retain the already real iconv solution, unless explicitly applying the separately audited source-exclusion patch. No reason to add StringNormalizer or widen to speech-required.config (which includes VITS).

First model-loading test must use exactly the hashed converted artifacts and preserve their disabled optimization contract. If session settings or a different ONNX input enable graph transformations, newly fused/contrib kernels may be introduced: regenerate the required set for that exact conversion/optimization policy, rather than assuming these rows cover it. The generator's auxiliary required kernels are not proof of every possible optimizer fusion. Runtime I/O/type/allocator checks and actual ASR correctness have not been established by host conversion.

This delivery is read-only source/record analysis and streaming file hashing. No model parsing/inference, network, SDK or device operation was executed. inputs.json freezes source/config/log evidence; verification.json freezes the two model hashes and parsed config rows. Root retains responsibility for new generation, configuration, compilation, final linkage and board validation.
