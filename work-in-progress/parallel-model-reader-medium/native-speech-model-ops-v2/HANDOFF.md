# Actual speech ONNX operator inventory

Completed with official ONNX Python1.16.2 / protobuf4.25.3 from the root-installed parser directory. This host parsing version is distinct from target ONNX1.15.0. The install report hash is in parser-input.json. No inference, shape inference, checker rewrite, model copying, or external tensor loading occurred; load_model(..., load_external_data=False). Model bytes were streamed for SHA256 before and after parsing, matching each other and the original model audit.

| Model | Nodes | Operator groups | Graphs | Local functions | Used opset |
|---|---:|---:|---:|---:|---|
| Paraformer encoder.int8 |3389|25|1|0|default ONNX14|
| Paraformer decoder.int8 |1488|24|1|0|default ONNX14|
| VITS model |4896|51|1|0|default ONNX13|

All three contain zero StringNormalizer nodes and zero external-data TensorProto declarations among graph initializers/sparse values and tensor attributes. No subgraphs were encountered; the parser traverses GRAPH/GRAPHS recursively and function bodies. Extra Paraformer imports (com.microsoft/training/etc.) are declarations, not evidence of used custom kernels: actual nodes use only the empty/default ONNX domain. Full raw imports remain recorded. Training-info counts are included in each report; this inventory concerns inference graphs.

encoder.json/decoder.json/vits.json preserve each node's scope/name/domain/op/opset/input/output names, every declared input/output/value_info type and shape, and tensor initializer/attribute dtype/dims/external metadata. No tensor contents or weight arrays are exported. The tensor dtype counts in summary.json count initializer/attribute tensors, not the inferred type of every activation: encoder FLOAT963/INT64308/UINT8400; decoder FLOAT455/INT64149/UINT8164; VITS FLOAT818/INT641171/INT327. operator-type-summary.json explicitly counts unannotated node outputs and preserves declared value types. Do not treat missing intermediate type metadata as a verified type-reduction map.

*-required.config and speech-required.config group actual used operators by imported opset, normalize the standard empty domain to ai.onnx for the ORT reduction config, and intentionally do not reduce types. Union contains two lines (opsets13/14). Paraformer requires DynamicQuantizeLinear and MatMulInteger; VITS includes ConvTranspose, RandomNormalLike, ScatterND and many shape/index/arithmetic operators absent from Add gate. These are necessary source-model kernels, not proof of complete optimizer/runtime closure. Use upstream full-build reduction generation to retain any optimizer/layout-added kernels, then real target load/run validation. StringNormalizer absence supports an optional scope-specific exclusion only after generated registration and source/link checks; it does not prove no other component can use Iconv.

Scripts: parse.py loads models only through ONNX parser; summarize.py produces config lists and type coverage. Execute with the installed Codex Python and -B; parser adds the explicit trusted package directory to sys.path. Parent's install report remains the parser provenance. No dependency/model downloads. Prior v1 parser-blocked evidence remains unchanged.

This is a reliable graph metadata inventory, not model validity/performance/native ASR/TTS acceptance. Target schemas/kernels, memory requirements, static link closure, real audio and streaming runtime still need separate validation.
