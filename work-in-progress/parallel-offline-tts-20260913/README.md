# Parallel offline TTS candidate — 2026-09-13

The staged read-only asset image, exact NuttX API/configuration, address
layout, and dynamic ASCII SSID limitation are documented in
`ROMFS_LAYOUT.md`. Machine-readable checks are in `romfs-audit.json`; rerun
them with `python romfs_audit.py`.

This directory is an isolated review candidate. It reuses the current formal
`app/voicelink` TTS C contract and implementation; it has not been added to the
formal CMake target and no SDK, firmware, device, or other project directory was
changed by this work.

## Result

`python verify.py` passes these host checks:

- fake Sherpa C API contract tests at `-O0` and `-O2`;
- actual Sherpa-ONNX 1.12.14 C API initialization and PCM generation from the
  original ONNX VITS model;
- actual initialization and PCM generation from the 31 MB ORT-format conversion.

Both real runs use the Chinese text `你好，网络配置已开始。`, return non-empty,
non-silent PCM, and report the model-declared 8000 Hz sample rate. Exact frame
counts differ between invocations because VITS synthesis uses noise inputs.
`verification.json` records commands, exit codes, logs, and all input hashes.

## Locked assets

The compatible asset family is `vits-icefall-zh-aishell3`:

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `vits.ort` | 31,190,816 | `97084af57de4135fc9217851386b1f6d511ae22eba01d9c5d9edf04f0e2adc63` |
| `model.onnx` | 30,482,262 | `5511d651b7840c0a93a6bbfd4afd070a2c7f39ca1ec3ff2ecd73191519bbb852` |
| `tokens.txt` | 1,671 | `50b45a7b7de1752fd3c7b4755661c285f1547f59186eca2281089a81307ad953` |
| `lexicon.txt` | 2,042,943 | `ab2e61d357551e7b24ddd965d924aca784c20165ff58c150794e539c6b5e9e35` |
| `rule.far` | 180,717,014 | `b090ed05e333fe125b62d8b1de5f1a1d4579fb237c606e7ac0b84707c863a01f` |

The model, tokens, and lexicon are sufficient for the simple Chinese sentence
used here. Full number/date/phone normalization also needs `rule.far`. The
current `k7_tts_request` contract has no `rule_fsts` field, so the candidate does
not claim normalized synthesis for those inputs. Adding that optional field, or
setting a product-owned fixed FAR path before creating the TTS instance, is a
required design decision before formal integration.

## ARM64 and link boundary

`python arm64_audit.py` compiled the exact candidate implementation with the
current `voice-ui-connect` ARM64 flags. Because the synced Ubuntu project does
not yet contain the new public TTS header, the script materializes that exact
header text into the translation unit before compilation. Source and header
hashes are recorded separately.

The 346,880-byte ARM64 object has SHA-256
`d7178dec47325e321722681996e58f99bfb2feba92a3e6b365242e20d23fc7c5`.
Demand-linking it with the current ASR runtime produces a 48,406,328-byte
relocatable object with SHA-256
`02f6777d0770a11616a6e8e9de505eacb6b1f17b53b9fe30ffeb8da832a1d734`.
The combination adds no strong undefined symbol to the current runtime's set,
contains one strong `__emutls_get_address`, one `k7_tts_synthesize`, and retains
both `.eh_frame` and `.gcc_except_table`. See `arm64-audit.json`.

The existing Ubuntu tree was inspected read-only. Its historical 47,967,336-byte
`link1/session.o` has SHA-256
`e43242de83135f400ee8c72668813d92c534f6b6f0020e3525f14904d6a4c767` and
exports the four C API symbols used by this wrapper. The historical audit found
393 strong undefined symbols and found definitions for all of them in its SDK
inventory. That object is an ASR+VITS relocatable demand link built around an old
probe. It is not a final firmware link and was never used to run a TTS model.
See `ubuntu-readonly.json`.

The audit streamed source and objects over SSH and used anonymous Linux memfd
handles, so the Ubuntu SDK/tree remained read-only. The actual static closure is
already present in the current ASR runtime: Sherpa C API/core, ORT with VITS
operator registration, FST/FAR/kaldifst, sentencepiece, iconv/locale shims, and
the custom emulated-TLS object. Final firmware still needs libc++, libc++abi,
libm, libgcc, and normal NuttX symbols.

The candidate object's 13 strong undefined symbols are the four Sherpa TTS C
entry points, `_Unwind_Resume`, `std::bad_alloc` RTTI, the C++ exception
personality/catch functions, `memset`, `strnlen`, and two pthread mutex calls.
All were already represented or defined in the current runtime/final firmware
closure. This relocatable link does not replace a final ELF link audit.

`RESOURCE_LOADING.md` explains why the current `k7ram:tts` and `/tmp` paths are
not yet real resource hooks and gives the smallest reusable ASR-derived design.

## Unfinished acceptance

- no final firmware link or CMake integration;
- no board model initialization, inference timing, peak-memory measurement,
  cancellation latency, speaker playback, or repeated-call cleanup test;
- no decision or test for `rule.far` normalization;
- model assets still live outside the unified project and have no accepted
  read-only board storage/loading path.

Host success must not be reported as ARM64 or device success.
