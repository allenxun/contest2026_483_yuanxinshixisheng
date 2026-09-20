# Native TTS model-memory candidate — 2026-09-13

This directory is an isolated source candidate. It does not alter the formal
Sherpa source, SDK, firmware, or device.

## Root cause

The spoken-TTS board profile has a roughly 126 MiB ordinary NuttX heap and a
separate 512 MiB model arena. The failing TTS call left the model arena at
536,870,144 free bytes except for allocator metadata, so the failure occurred
before ORT used that arena.

The current VITS constructor uses a new `Ort::Env` and unmodified Sherpa
`GetSessionOptions()`. `num_threads=1` only limits intra/inter-op workers. ORT
still defaults to Level-3 graph optimization, memory patterns, the CPU arena,
and prepacking. More importantly, the TTS Env never registers the K7 model
allocator, so model initialization is charged to the ordinary heap. The
31,190,816-byte ORT model is also read into a temporary vector and copied again
unless the direct-byte options are set. Historical Windows measurements support
the scale of the problem: this same TTS family used 303–315 MiB peak private
memory despite the model being about 31 MiB.

The wrapper creates and destroys `SherpaOnnxOfflineTts` for every text segment;
its fixed 30-second PCM vector is only 480,000 bytes and cannot explain an
initialization failure of this size. In the locked Sherpa source,
`GetSessionOptionsImpl()` sets only the two thread counts for the CPU provider.
ORT 1.17.1 therefore retains its declared defaults: memory pattern enabled, CPU
arena enabled, and graph optimization Level 3. Its ORT-format loader also copies
the supplied flatbuffer unless `session.use_ort_model_bytes_directly=1`.

The current runtime remains a full, reduced-operator CPU build with MLAS; it is
not an ORT minimal build. Since `vits.ort` is already ORT format, a later
model-specific minimal build can reduce binary/parser surface, but it does not
route Session allocations into the K7 arena and is not the first fix for this
failure. Reusing the existing runtime and changing the Env/Session configuration
keeps the build change narrow.

## Candidate behavior

`offline-tts-vits-model.patch` adds an opt-in `K7_TTS_NATIVE_STORAGE` path. It:

- accepts only the already mounted `/mnt/k7tts/vits.ort` model path;
- points ORT directly at the verified ROMFS payload at `0x96000730`, length
  31,190,816 bytes, avoiding `ReadFile()` and a second model copy;
- registers `k7_model_alloc` with the VITS session's own Env and selects it with
  `session.use_env_allocators=1`;
- selects ORT format, direct model bytes, and direct initializers;
- forces sequential execution, one intra-op thread, one inter-op thread, and
  `ORT_DISABLE_ALL`;
- disables memory-pattern capture because every current wrapper request creates
  a one-shot Session, so no later run can reuse its learned pattern;
- prints bounded allocator peak/failure telemetry without model path or text.

The ROMFS pointer is valid for the Session lifetime because the image is staged
RAM owned by the firmware and is not changed after the whole-image CRC gate.
The model offset and length are compile-time checked against the generated ROMFS
descriptor, including its exact base address, byte count, and expected CRC32.
Tokens and lexicon continue through the mounted read-only ROMFS.

The member order is part of the contract. `ModelStorage` is declared before
`Ort::Env`, while the Session remains later in the class. Reverse destruction is
therefore Session -> Env -> allocator bookkeeping, including constructor unwind.

The caller must also hold the workspace's shared ASR/TTS lifecycle gate from
before Session creation through Session destruction. The mutex in this candidate
only protects this allocator adapter's records; it is not the cross-engine gate.
Do not integrate this patch alone if ASR can still own allocations in the same
arena.

## Build integration

Apply the patch only to the locked Sherpa source whose
`offline-tts-vits-model.cc` SHA-256 is
`0dbe70a46b0f57738d8a56ce28fd0b3db1e896fa70c87f68787c68456f11d8d9`.
Compile that translation unit with:

```text
-DK7_TTS_NATIVE_STORAGE=1
-I<directory-containing-native_tts_model_storage.hpp>
-I<directory-containing-k7tts_assets_generated.h>
```

Use the existing VITS operator registration and full ORT runtime. This is a
source-level memory-routing change; rebuilding only the top-level wrapper will
not include it. Do not enable `session.disable_prepacking` in the first board
attempt: it may reduce persistent weight copies but can change latency
substantially, and direct initializers plus arena routing should be measured
first. `DisableCpuMemArena()` is also omitted because `use_env_allocators=1`
replaces the CPU allocator with the registered bounded allocator; disabling the
CPU arena separately does not fix the observed pre-Session ordinary-heap path.

## Required verification

Before treating this as fixed, compile the patched Sherpa object and verify the
final relocatable object/ELF contains the new `TTS_STORAGE` string and the four
session option keys. Then run `tts-smoke` with the existing ROMFS CRC gate and
record `peak`, `records`, `failures`, `failed_bytes`, and `reason`. Acceptance
requires non-empty 8 kHz audio, audible playback, `live=0`, `failures=0`, and
unchanged ASR model CRCs. Repeated create/generate/destroy calls still need a
separate cleanup/TLS test. This candidate has not been compiled for ARM64 and
has not run on the board.

`test_options.cpp` is a host contract test for the exact pointer, path gate,
option sequence, four config entries, allocator accounting, and zero-live
cleanup. Its fake arena is test-only and does not estimate board peak memory.
