# Codec quarter-density capture review

## Judgment

The inspected codec configuration is internally consistent with 16 kHz stereo I2S using 32-bit slots. The frozen manufacturer guide and official SDK codec implementation do **not** define an output mode that emits one L/R pair followed by six zero words. No codec register change is justified by that pattern alone. This does not prove the physical clocks or codec output are correct: configured constants and register readbacks are not waveform measurements.

Root reports the current board buffer has strict `[L,R,0,0,0,0,0,0]` grouping, nonzero frame positions at index 0 modulo 4, initially -1 at the first 720 valid positions, then changing apparently left-aligned 24-bit values. This report is input evidence, not independently captured or reprocessed by this review. No hardware, SDK, PIO changes, model access or downloads occurred.

## Register and source correspondence

| Register | Intended current value | Source interpretation and consequence |
|---|---|---|
|00|36; VMID mode35|SameFs=1, DACMCLK=1, reference enabled. Shared sample-rate clock uses DAC domain; VMID change affects bias divider, not a four-frame interleave. 02=00 retains the selected clock domain. Prior frozen reference review records the Rev5 field audit.|
|08|00|Slave, MCLK divide-by-two clear, normal polarity, BCLKDIV=0. Manufacturer guide pp7–9 explicitly requires automatic MCLK/SCLK detection with BCLKDIV zero in slave mode. Do not set a master divider to4 merely because MCLK/BCLK=4.|
|0c|10|Official SDK `es8323_pcm_hw_params`, S32_LE: ADC serial word-length value0x10; I2S format bits remain0. This is one word per channel per LRCK cycle, not four audio frames per conversion.|
|0d|02|Official coefficient row `{4096000,16000,256,0x2,0x0}`. USB mode clear; guide p8 says slave detects MCLK/LRCK.|
|17|20|Official S32_LE DAC serial word-length value0x20 with I2S format bits0. DAC serial word length does not select sparse ADC frame emission.|
|18|02|Same coefficient as ADC; matches shared Fs.|
|2b|80|Guide p8: one physical LRCK pin; bit7 selects shared LRCK and bit6 must0. Consistent with80.|

Official source is `parallel-k7-audio/sources/kernel-6.1/sound/soc/codecs/es8323.c`, especially coefficient table line393 and hw_params lines565–632. It is an ES8323-named compatibility driver used by the board SDK, not independent proof of the package marking. Guide is the frozen ES8388 2011-06-17 manufacturer document mirrored by Radxa; exact local PDF/text hashes are in inputs.json. No fresh datasheet claims are invented.

Arithmetic: MCLK/Fs=4096000/16000=256; BCLK/Fs=1024000/16000=64; MCLK/BCLK=4; each full LRCK cycle carries two32-bit slots. 24-bit converter precision transported in a32-bit word does not imply dropping three of every four **stereo frames**. The changing words' apparent precision alone does not establish sign/bit alignment, correct LRCK or sample rate.

The formal PIO source requests SBW32/VDW32/SNB2, frame width64 and pulse width32. That is the intended framing; this review does not certify those fields' hardware behavior or FIFO addressing. C owns that investigation. The WAV header's16000 is a software declaration and must not be treated as independent timing evidence.

## Falsifiable next check, without speculative codec changes

1. Preserve codec registers and the full original buffer. Record after-arm full bytes00/02/08/0c/0d/17/18/2b with the exact mode; validate08 low5 bits as well as the currently checked e0 mask, and2b c0 bits. Unexpected readback would falsify the assumed configuration before changing ratios.
2. Have C establish whether each physical LRCK period places exactly two words into the selected RX FIFO and whether reads drain only that FIFO. If consecutive FIFO samples contain L/R each cycle but the exported array inserts six zeros, the codec-clock explanation is falsified. Do not remove every three zero frames and label the result16k without proving this mapping.
3. If physical clock measurement is available under root authorization, count complete LRCK periods rather than both edges: expected16k periods/s,64 BCLK periods/LRCK period and4 MCLK/BCLK. A measured4k LRCK or256 BCLK/LRCK disproves the software16k/64-clock claim and directs investigation to source/framing. Asynchronous short GPIO loops are not a substitute for these frequency/edge-ratio observations.
4. If the physical clocks match and the codec SDOUT itself has an L/R pair on every LRCK cycle while RAM is sparse, the issue lies after serial output. Conversely, if SDOUT itself is silent for three complete cycles after each active pair, only then revisit codec clock acquisition/state, with that waveform and full readbacks; the present documents do not identify a magic register repair.

The initial720 valid -1 positions cannot yet be converted to a settling time: at16k consecutive real frames this is45ms, while if they are every fourth physical16k frame it is180ms. Capture start timestamps and established FIFO mapping are prerequisites. Keep the prefix as evidence; don't call it VMID settling based only on these arithmetic alternatives.

Deliverable is a read-only audit and input snapshots, no patch. No claim of recording intelligibility or board ASR.
