# LIN2/RIN2 16 kHz capture review

Scope: local PCM capture only. MIC connection is accepted as confirmed. No request to reconnect it; no TTS, offline model or Agent dependency. This directory contains a **non-executable reference plan** using the existing codec transaction engine, not a hardware-ready implementation. Nothing in formal source/SDK/device/central logs was changed.

## Candidate and sources

capture_reference.c constructs15 reference writes, with hardware mode, reviews=0, all steps KC_REFERENCE_ONLY, no readback rules and no guessed delays. kc_start rejects it before any callback. Its purpose is to give the integrator concrete values and ordering to review; it must never be enabled by mechanically setting review bits. Missing reset baseline, ADC settling, ALC state, power/format verification and stop ownership are intentional unresolved conditions.

Source101 is the recovered ES8388 User Guide (Everest-branded Radxa mirror,2011-06-17), p26 recording flow. Source102 is p20 differential pair2 alternative. Source103 is the frozen official Linux es8323.c I2S/S16 fields and data-map controls. The source is bound to ES8388 by board DTS/schematic and is a reference, not proof that every ES8323 behavior applies to the installed revision. inputs.json hashes all consumed code/document inputs; previous audio-codec-plan-v1 and audio-codec-datasheet-v1 remain frozen.

| Ordered reference operation | Register=value | Status |
| --- | --- | --- |
| Codec slave, digital block reset, shared LRCK |08=00,02=f3,2b=80| Guide p26; clocks must already be coordinated. |
| Reference and analog configuration |00=05,01=40| Guide p26; full-byte applicability and reset/settling unresolved. |
| ADC/analog input power |03=00| Guide p26; board uses external bias, do not equate codec bias enable with correct microphone voltage. |
| Differential input pair2 |0a=f0,0b=82| Guide p20; explicit LIN2/RIN2 selection replaces p26 Line1 example. |
| Initial fixed PGA choice |09=00| Guide p26 zero-gain reference; not microphone sensitivity calibration; ALC state unresolved. |
| I2S,16-bit, separate L/R ADC data |0c=0c| Derived from Linux I2S and S16 controls, data selection0. Replaces guide24-bit example; not blind use of contradictory0x40 sample. |
| Rate ratio, digital volume |0d=02,10=00,11=00| Guide ratio256 and zero-dB reference. |
| ADC unmute then digital recording release |0f=30,02=55| Guide p26 ordering; the intervening optional ALC configuration is NOT supplied. |

Requested profile:16,000 frames/s, two16-bit slots, MCLK4,096,000Hz, BCLK512,000Hz;4 bytes/frame and64,000 bytes/s. These are arithmetic/request values, not measured clocks. Keep stereo interleaving until actual channel behavior is established; select/mix mono later only after evaluating both channels.16-bit PCM storage does not alone establish16-bit wire slots.

## Stop and recovery contract

Guide p27 reference order is ADC mute0f=34 and DAC mute19=36, digital reset02=f3, ADC/analog/bias powerdown03=fc, DAC outputs disabled04=c0. No stop array is exported as runnable code: existing engine cleanup is KC_QUIESCE, not a second kc_start plan. Do not start a second transaction to bypass its ownership.

Main session must map this reference to the actual serial owner: prohibit new capture submissions, retain clocks needed for codec control, stop/confirm outstanding receive and DMA ownership, perform reviewed codec shutdown, then release clock/power resources. The precise mute-versus-receiver-stop order and timeouts need A/C adapter review. Failed/late quiescence retains ownership and prevents restart; reported cancel is not confirmed stop. In capture-only use, whether guide DAC mute/power writes can safely be omitted remains an explicit review point. External amplifier remains disabled throughout.

## Readback: known fields versus unapproved policy

The recovered datasheet establishes I2C register reads, but no actual K7 read transaction or populated revision has been verified here. Candidate field masks for review are0x0a:f0 (PGA selectors),0x0b:80 (pair),0x0c:dc (data map and word length),0x0f:04 (mute). These are **field-specific comparison suggestions**, not full-byte allowed masks or granted readback rules. For I2S/polarity, additionally review0x0c:23. A final whitelist must tie each mask to the versioned register definition and expected stable state, exclude reserved/reset/self-changing bits, and account for all earlier writes.

No reliable source in this frozen set establishes an unconditional ff readback mask for every control/power register, settling interval after arbitrary partial reset, or hardware reset-bit read behavior. Do not infer readability from regmap cache hits.0x01=40 uses a bit not described in the inspected Rev5 named-field table; reconcile this guide/full-write difference before granting a full-value check. Linux's unexplained0x35 write remains excluded.

## Conflicts and decisions still needed

- Guide p20 writes0x0c=40 while its comment describes00 and separate L/R data. This candidate explicitly chooses separate data and16-bit format, resulting0c; it is a documented adaptation still needing target format verification.
- The same ALC sample writes0x13=a0 while its comment claimsc0. Its0x12=e2 gain description also does not straightforwardly match the earlier voice-table recommendation. No ALC bytes or blanket21dB gain are added here. An inherited ALC state would invalidate a claimed fixed-gain baseline, so the reference cannot run as-is.
- Guide p26 omits a complete cold-reset/settling proof; frozen Linux uses a different probe/standby sequence with unrelated output writes. Neither permits invented timing or a copy of the whole Linux probe.
- Actual codec revision, powered rail/bias levels and resulting signal quality remain unmeasured. MIC presence is already known; these are electrical/behavior checks, not another connection question.

## Executable next steps for main session

1. Resolve the above register/revision discrepancies against the recovered documents; define a known reset baseline and explicit fixed-gain/ALC choice with settling requirements. Record provenance per step/read rule.
2. Reconcile the16kHz two-slot profile with C's SAI implementation and A's bounded combined-read/write callbacks. Add no codec-specific pinmux/SAI changes here.
3. Implement KC_POWER_PREPARE/CAPTURE_PREPARE/QUIESCE with one serialized owner and retained buffers until completion. Populate a separately reviewed plan only once these controls and masks are justified.
4. Main session then performs a finite small PCM capture, records actual I2C errors/readback, sample count/channel layout/clipping and stop confirmation. This would establish local capture evidence only, not recognition or cloud-service acceptance.

## Host verification

run_tests.py compiles unchanged codec_txn.c with this candidate and test_reference.c using GCC C11 O2 and strict warnings. The test checks15 reference steps, pair2/format values, reviews0/read_count0, and real-engine rejection KC_NOT_READY with zero callbacks and unchanged transaction ID/state. Compile limit30s; run limit15s; argv/output in results.json. No simulation plan was promoted, no fake ADC data accepted, and no target compilation or hardware execution occurred. The test validates gating, not analog correctness or PCM capture.
