# K7 offline TTS `std::bad_alloc` analysis

Date: 2026-09-13. This is a candidate-only audit. No formal source, SDK, firmware,
or device state was changed.

## Finding

The observed failure is on the ordinary NuttX heap path, before the 512 MiB K7
model arena is used. The decisive log sequence is:

```
MODEL DDR base=60000000 bytes=536870912 free=0 initialized=0
Exception during initialization: std::bad_alloc
VOICE_TTS result=-5
```

After the failed TTS call, `k7mem status` reports the arena initialized with
536,870,144 bytes free. Therefore the arena was neither exhausted nor used by
the failed ORT session. The board's low RAM interval is only 132,120,576 bytes
in `velavision_wifi_ip_local/defconfig`, and it also contains the image and the
ordinary heap.

The unmodified VITS implementation first calls `ReadFile()` into a
`std::vector<uint8_t>` and then creates `Ort::Session` without a K7 allocator.
Both the 31,190,816-byte model copy and ORT initialization allocations therefore
come from the ordinary heap. This explains `std::bad_alloc` without any ASR
lifecycle present.

## Minimal directly implementable fix

Use the same custom allocator pattern already validated by the native ASR:

1. Initialize the K7 arena before loading VITS.
2. Register an `OrtAllocator` backed by `k7_model_alloc`/`k7_model_free` on the
   VITS `OrtEnv`.
3. Pass the persistent, verified model bytes at ROMFS image offset `0x730`
   (`0x96000730`) directly to ORT, avoiding both the ordinary-heap `ReadFile`
   vector and a second 31,190,816-byte arena copy.
4. Set `session.use_env_allocators=1`, `session.load_model_format=ORT`,
   `session.use_ort_model_bytes_directly=1`, and
   `session.use_ort_model_bytes_for_initializers=1`.
5. Keep the model-byte lease alive until after `Ort::Session` destruction.
6. Serialize ASR and TTS model lifecycles; both share the same global arena.

The audited `work-in-progress/tts-arena-direct-20260913/native_tts_storage.hpp`
implements this preferred direct-ROMFS approach. Its model pointer is 16-byte
aligned, lies outside allocator `[0x60000000,0x80000000)`, stays mapped for the
Session lifetime, and is protected by both the ROMFS mount CRC and an exact
model SHA-256 check. Its containing VITS object declares storage before Env and
Session, giving the required reverse destruction order. No code-blocking issue
was found in this candidate.

Files in this independent WIP provide a conservative fallback and audit trail:

- `native_tts_model_storage.hpp`: 512 MiB bounded allocator, ROMFS-to-arena
  read, model-size lock, and peak/failure telemetry. This fallback consumes an
  extra 31,190,816 bytes and should only be used if direct mapped bytes fail.
- `offline-tts-vits-model.cc`: a guarded `K7_TTS_NATIVE_STORAGE` patch around
  the upstream VITS constructor; the normal implementation remains available
  when the guard is absent.
- `shared_runtime.hpp`: the already-tested fixed-capacity allocator registry.

The storage record capacity is 2,048. The previous ASR board run peaked at 1,264
records, so this removes a known capacity mismatch while preserving a bounded
metadata table. The destructor releases the model lease before printing final
telemetry; a successful cleanup should report `live=0`.

## Required ASR compatibility correction

The current native ASR storage hardcodes a 768 MiB runtime quota. A spoken-flow
configuration with `K7_MODEL_ARENA_SIZE=512 MiB` makes `Runtime::init()` reject
that quota as larger than its backing window, before loading either ASR model.
`native_asr_model_storage.quota-fixed.hpp` changes the quota to
`K7_MODEL_ARENA_SIZE`.

This quota is consistent with the prior measured ASR peak of 468,101,988 bytes:
the remaining margin is 68,768,924 bytes. It is a real but narrow margin, so ASR
and TTS must be created and destroyed sequentially and `live=0` must be checked
between them.

## Memory evidence and acceptance gate

The existing Windows TTS CLI run with this model observed 311,459,840 bytes RSS
and 303,878,144 bytes private memory. That is whole-process host evidence rather
than a board allocator measurement, but it supports trying the 512 MiB arena
before replacing the model.

The first board acceptance run of the allocator candidate must capture:

- arena `peak`, `live`, `peak_count`, `failures`, `failed_bytes`, and failure
  reason for VITS creation plus one generation;
- `live=0` after TTS destruction;
- a following ASR create/run/destroy with its historical result and `live=0`;
- no concurrent ASR/TTS session.

Do not enlarge the arena or alter ASR staging until this scoped telemetry shows
an actual 512 MiB shortage. If initialization still fails, the allocator's
`failed_bytes` and reason distinguish capacity, record-table exhaustion, bad
alignment, and foreign-pointer errors.

## Model audit

The staged ORT model is 31,190,816 bytes, SHA-256
`97084af57de4135fc9217851386b1f6d511ae22eba01d9c5d9edf04f0e2adc63`.
The local workspace contains no smaller downloaded Chinese TTS ONNX/ORT model.
The current asset is already smaller on disk than the Chinese VITS models in the
official Sherpa catalog. Switching to Piper or Matcha would also change frontend
assets, phonemization and possibly the reduced operator closure. It is not the
minimal repair for this failure.

Catalog references:

- https://github.com/k2-fsa/sherpa/blob/master/docs/source/onnx/tts/pretrained_models/vits.rst
- https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese/index.html

## Candidate verification boundary

An earlier revision of the guarded VITS source compiled successfully with the
current AArch64 NuttX toolchain and locked ORT headers. The final revision only
changes deterministic file closing and teardown telemetry; guest SSH became
unreachable before it could be recopied and recompiled. Consequently final
ARM64 compilation and board execution remain open. The candidate has not been
linked into formal firmware and has not run on hardware.
