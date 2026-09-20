# TTS direct-ROMFS / shared-arena candidate

This isolated candidate addresses the board `bad_alloc` seen while
`k7_model_available()` still reported the full 536,870,144-byte staged arena.
That observation proves the failing TTS path did not allocate from the model
arena. The current unmodified VITS code creates its own `Ort::Env`, reads the
31,190,816-byte model into a `std::vector`, and never registers the K7 arena.

## Candidate behavior

`native_tts_storage.hpp` registers the same bounded allocator used by ASR on
the VITS `Ort::Env`. It passes the persistent ROMFS model bytes directly from
`0x96000730` and enables direct ORT-format model/initializer bytes. The whole
ROMFS CRC remains the mount gate; storage independently checks the exact model
SHA-256 before creating a session. No TTS allocation may use or overwrite the
ASR encoder at `0x80000000`, decoder at `0x90000000`, or the ROMFS at
`0x96000000`.

The allocator compile contract is exactly `[0x60000000,0x80000000)`. The ASR
storage patch replaces its stale 768 MiB runtime quota with
`K7_MODEL_ARENA_SIZE` and requires the runtime object to be rebuilt against the
staged-assets header. Reusing the old opaque ASR object is unsafe because that
object was compiled with a 1 GiB arena end even though the running heap is only
512 MiB.

`speech_runtime_gate` serializes complete ASR and TTS object lifetimes. It is
stronger than the two current private mutexes, which permit the two runtimes to
consume the same arena concurrently.

The patch files describe the required Sherpa and wrapper changes. The VITS
model storage member must be declared before `Ort::Env`; the Session is
destroyed first, then Env, then the registered allocator. Tokens and lexicon
remain read-only ROMFS file paths. They are small enough for the ordinary heap
and do not need a private URI implementation.

## Required build and board gates

Build a new combined runtime from source with
`K7_TTS_NATIVE_STORAGE=1`, `K7_ASR_NATIVE_STORAGE=1`, and
`CONFIG_EXAMPLES_K7VOICE_STAGED_ASSETS=1`; do not append this candidate to the
old combined object. The final link must contain one speech gate, one emulated
TLS definition, and no duplicate VITS/Paraformer implementations.

On board, first run only `tts-smoke`. Require model SHA success, nonzero arena
peak below 512 MiB, zero live bytes after destruction, no allocation failures,
audible PCM, and unchanged CRCs for encoder, decoder, and ROMFS. Then run one
fixed ASR regression under the 512 MiB compile contract; its prior measured
peak was 468,101,988 bytes, leaving 68,768,924 bytes before heap metadata.
Finally repeat TTS -> ASR -> TTS to verify arena reuse and TLS cleanup. These
tests have not been run by this candidate.
