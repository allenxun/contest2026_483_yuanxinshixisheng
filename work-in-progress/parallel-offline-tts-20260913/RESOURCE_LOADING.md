# Native TTS resource loading audit

## What `k7ram:encoder` actually does

There is no general `k7ram:` resolver in the current runtime. The ASR path is a
model-specific source modification:

1. `native_asr_runtime.cpp` supplies the sentinel strings `k7ram:encoder` and
   `k7ram:decoder`.
2. `online-paraformer-model-config.cc`, under `K7_ASR_NATIVE_STORAGE`, accepts
   exactly those two strings without calling `FileExists`.
3. `online-paraformer-model.cc` bypasses `ReadFile` entirely and calls
   `ModelStorage::initialize`, then constructs `Ort::Session` from a pointer and
   byte length.
4. `native_model_storage.hpp` hashes fixed source regions at `0x80000000` and
   `0x90000000`, initializes the model arena, copies both models into persistent
   arena allocations, hashes the copies again, and selects ORT-format,
   single-thread, sequential, direct-byte session options.

The locked source hashes are recorded by
`work-in-progress/native-asr-recognizer/compile-attempt2.json`. The current
runtime uses the patched Sherpa core archive from
`/home/swl/openvela/work/native-asr-recognizer/link2/libsherpa-onnx-core.a`.

## Why the proposed TTS paths do not work yet

The unmodified VITS code follows three independent filesystem paths:

- `OfflineTtsVitsModelConfig::Validate` calls `FileExists` for the model and
  tokens;
- `OfflineTtsVitsModel::Impl` calls `ReadFile(model)` before constructing the
  ORT session;
- `Lexicon` opens `tokens` and `lexicon` with `std::ifstream`.

Consequently `k7ram:tts` has no resolver and fails validation/opening. The paths
`/tmp/tts-tokens.txt` and `/tmp/tts-lexicon.txt` work only if another component
has created real files there. No current loader creates those files, and doing
so would add an unverified RAM copy and lifecycle.

## Smallest reusable implementation

Use a TTS-specific variant of the proven ASR memory path rather than teaching
all libc file calls a private URI:

1. Define a read-only resource descriptor containing address, exact length, and
   expected SHA-256 for `vits.ort`, `tokens.txt`, and `lexicon.txt`. The OTG
   package owner must assign verified non-overlapping addresses; this audit does
   not guess them.
2. Extend `OfflineTtsVitsModelConfig::Validate` to accept only the exact native
   sentinel when the native TTS storage macro is enabled.
3. In `OfflineTtsVitsModel`, hash the staged 31,190,816-byte ORT model, reserve
   persistent model-arena storage, copy and re-hash it, apply the same ORT
   direct-byte/session options, and construct `Ort::Session(env, bytes, size,
   options)`. Preserve the storage/allocator declaration order used by ASR.
4. Add an explicit `Lexicon` buffer/stream constructor. Parse the verified
   1,671-byte tokens and 2,042,943-byte lexicon buffers with bounded input
   streams, then select that constructor in `OfflineTtsVitsImpl::InitFrontend`.
   This avoids filesystem aliases and avoids a second temporary file copy.
5. Serialize ASR and TTS model ownership at the speech-runtime level. Their
   current per-function mutexes do not prevent simultaneous allocations from
   separate ASR and TTS calls, even though the underlying model arena is shared.

The full 180,717,014-byte `rule.far` still has no buffer frontend in this plan.
For the first provisioning flow, render sequence numbers as Chinese words and
keep prompts free of dates/phone-number normalization. Never synthesize or log
the recognized password. This permits a bounded first version without claiming
general number normalization; adding FAR later requires a separate in-memory
FST/FAR reader and a measured memory budget.

## TLS and exception-table gates

The wrapper itself introduces no `__emutls_get_address` reference. The combined
relocatable object retains exactly the one strong custom definition already in
the current ASR runtime. TTS creates and destroys an ORT environment/session and
may exercise TLS objects in a different task, so repeated real TTS calls still
need the existing task-group TLS isolation/destructor checks. The custom TLS
implementation bounds each context to 256 blocks and 256 destructors; exceeding
either is a fail-stop risk that host model generation does not cover.

The candidate object contains `.eh_frame` and `.gcc_except_table` because it
catches allocation and other exceptions. After adding it to the firmware,
rerun the final ELF unwind audit: consolidated LSDA, no orphan LSDA, exact start
and end symbols, read-only mapped exception sections, unwind registration as the
first initializer, and runtime throw/catch proof. The current firmware's 26,754
FDE result applies only to the pre-TTS ELF.
