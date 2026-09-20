# ES8388 capture/playback plan audit

**Complete capture remains NOT_READY.** User confirmation that MIC is connected is accepted; it establishes connection presence, not actual codec revision, microphone polarity/type/bias voltage, powered ADC route, clocks, PCM capture, or safe stop. This candidate narrows previously unknown fields using the frozen official Linux source and schematic extracts. It does not rewrite the transaction engine, modify review flags, access devices/SDK, or build I2C/SAI adapters.

## What the sources establish

Sources are frozen under parallel-k7-codec/input/kernel-6.1 and parallel-k7-audio/sources; exact input hashes are in evidence/inputs.json. es8323.c/.h are GPL Linux source references; generated reference-sequences.txt contains verbatim function extracts under that original source license, not newly licensed target driver code. reference-fields.json is deliberately **not an executable kc_plan**: reviews=0, every field REFERENCE_ONLY, hardware_read_rules empty.

Schematic p32 labels U7000 ES8388, J7001 MIC2P→LIN2 pin22 and MIC2N→RIN2 pin21. The latter is a differential input, not a second independent microphone. Existing board report gives CE grounded/address0x10 and external bias resistors; physical board variant/loaded part and bias remain unmeasured. DTS's Main Mic/Headset Mic labels are graph names; their route list does not select the codec's differential mux or prove actual wiring. No replacement of the original board evidence is implied.

| Register field | Linux reference derivation | Candidate meaning / limit |
| --- | --- | --- |
| 0x0a ADCCONTROL2 [7:6], [5:4] | SOC_VALUE_ENUM selectors at shifts6/4, values0,1,3 | DifferentialL/R selects3: combined mask0xf0/value0xf0. Lower bits are not inferred. This is a field update description, not permission to hardware-read/modify/write. |
| 0x0b ADCCONTROL3 bit7 | Differential enum Line1/Line2 | Line2 mask/value0x80; route graph connects both LINPUT2 and RINPUT2. |
| 0x0b [4:3] | Stereo/MonoLeft/MonoRight enum | Stereo field0 under mask0x18 is one reference choice; desired channel mapping still needs capture verification. Do not infer 0x82 as a complete register solely from probe0x02. |
| 0x0c ADCCONTROL4 | ADC interface: I2S clear0x03; S16 clear0x1c/set0x0c; NB_NF clear0x20 | [7:6] are ADC data ordering; LeftRight selection0 is a separate field. Keeping arbitrary old upper bits could duplicate/swap channels. Hardware reset/retained-bit basis remains missing. |
| 0x08 MASTERMODE | Slave clears0x80; normal BCLK clears0x20 | hw_params subsequently reads &0x80 and may set0x40 for MCLK/2. Source transformation is not a measured clock mode. |
| 0x0d / 0x18 sample rate | coeff_div 4096000,16000,256,sr2,usb0 | Both ADC and DAC rate writes are0x02 for that exact reference pair. Initial DTS12.288MHz uses a different table coefficient0x06 at16k; do not pair it with0x02. |
| 0x0f ADCCONTROL7 bit2 | Capture Mute control | mask0x04/value0x04 mute, value0 unmute. This is separate from es8323_mute, which is a no-op; no_capture_mute=1 confirms automatic DAI capture mute cannot be relied upon. |
| 0x09 / 0x10 / 0x11 / 0x12..0x16 | PGA/digital volume/ALC controls and probe writes | Control locations are known; microphone-appropriate gains, ALC thresholds and anti-clipping profile are not approved. Probe0xea etc are not a safe new microphone calibration. |
| 0x03 ADCPOWER | DAPM ADC bits5/4 and ADC PGA bits7/6 are inverted power controls; micbias bit3 also inverted | These controls alone do not define the full byte, all analog dependencies, settling or shutdown order. External board bias is not automatically the DAPM Mic Bias output. |
| 0x17 DAC format / 0x27,0x2a mixers | S16 mask0x38/value0x18; playback mixer bit7, bypass bit6 | Describes playback digital path; cannot enable an amplifier or bypass route for capture by copying probe. |

MCLK=4.096MHz, LRCK=16kHz, BCLK=512kHz assumes two **16-bit slots**. It is not enough that PCM samples are16-bit: two32-bit slots would require1.024MHz BCLK. Clock ratio, I2S one-bit delay, polarity, actual slot width and MCLK continuity must be reconciled with C's SAI work. No SAI register proposal is included here.

## Sequence reconciliation, mute and stop

reference-sequences.txt retains complete reset, set_fmt, hw_params, mute, bias and probe function bodies rather than flattening branches into an invented recipe. Reset writes CONTROL1 0x80→0x00. Probe powers MCLK, resets, executes fixed control/ADC/DAC/output writes, waits18–20ms twice, then calls STANDBY. Many writes ignore errors; its 0x35=0xa0 write exceeds regmap.max_register0x34. These are reasons to audit the sequence, not to silently fix or run it.

Probe does not select the proposed LIN2/RIN2 differential fields (0x0a is written0, 0x0b0x02). DAPM later adjusts route/power according to stream/control state. Copying probe alone therefore does not establish the complete intended capture path. Its timing waits also do not identify which ADC transition requires what minimum settling interval in a capture-only sequence.

Linux BIAS_OFF order is ADCPOWER0xff, DACPOWER0xc0, CHIPLOPOW1/2 both0xff, CHIPPOWER0xff, ANAVOLMANAG0x7b. This is a reference power-down list, **not** an approved KC_QUIESCE or DMA ordering. Freeze further register operations on the serialized owner, keep amplifier disabled, arrange ADC mute while control clocks are valid if reviewed, stop acquisition and confirm DMA/buffer ownership returned, then use a reviewed codec power-down/clock-disable sequence. Exact ADC mute/SAI-stop relative timing and recovery from partial writes still need documentation/target checks; no guessed delays or safe-zero masks are supplied.

Playback remains separately unready: route DAC→mixers→LOUT2/ROUT2→external amp is documented; external amp actual model/load and output-gain constraints are not. Speaker GPIO delay30ms before enable and40ms after disable is Linux board policy, not codec mute. The task's capture baseline keeps amplification disabled. No playback-ready flag or safe audible level is generated.

## Readback policy and minimal plan assembly

Field masks above are **update masks derived from Linux controls**, not approved hardware readability masks. The regmap cache/default table and component_read calls cannot establish volatile/reserved/W1C/self-clearing/readable behavior of an actual ES8388 revision. Read_count stays0, and no register is promoted to KC_TARGET_REVIEWED. ACK at0x10 would establish a responder, not unique codec identity; do not invent a chip-ID register.

Do not reconstruct the engine. Once missing evidence is available, feed it a separate reviewed plan with explicit full write values from a known baseline and narrowly justified read rules. POWER_PREPARE must certify rails/amp-off; clock_ready must certify measured/requested format; INIT must cover reset/power and documented settling; CAPTURE must cover differential selection, data mapping, gain/mute and ADC power; CAPTURE_PREPARE must coordinate actual receiver readiness; QUIESCE must confirm old I/O exited. A mere extra KC_CAPTURE write does not satisfy this chain. All six review categories must be assessed individually, and existing deadline/cancellation/error cleanup behavior is retained.

## Information still needed to remove NOT_READY

1. Exact populated codec/board revision and a matching manufacturer register manual/errata: valid full-byte defaults, read/write/volatile/reserved masks, reset timing, analog sequencing and ADC settling, clock dividers, differential routing and power-down order. Earlier official datasheet retrieval failure remains unresolved; this bounded task used only frozen local sources.
2. Microphone type/polarity/rated bias and actual powered bias/rails; user-confirmed connected MIC does not provide these electrical facts. Select PGA/ALC/digital volume from a documented initial profile, then inspect bounded captured samples for clipping/channel mapping.
3. Confirmed clock/slot/format agreement with C and bounded I2C transaction/stop ownership from A; their work is not duplicated here. Readback rule approval must precede read verification.
4. Serialized hardware sequence and failure-cleanup review; successful I2C writes alone cannot prove analog readiness or capture. After prerequisites, main session performs finite PCM capture with no amplifier enable and labels actual evidence separately.

## Tests

Run the supplied run_tests.py with the configured workspace Python. It validates source anchors and all256 old-byte cases for each of8 field-update descriptions (2048 algebra checks), extracts reference bodies, snapshots input hashes, then compiles/executes the **unchanged real codec_txn.c and existing C tests** into this directory. GCC O2 strict warnings passes2270 checks/0 failures, including hardware-reference NOT_READY and simulated faults. Compile timeout30s, execute15s; exact commands/output are evidence/results.json. Field algebra is a mock description check, not Linux/codec hardware execution. No new transaction engine, reviewed hardware plan, SDK build, I2C/SAI run, or microphone recording was performed.
