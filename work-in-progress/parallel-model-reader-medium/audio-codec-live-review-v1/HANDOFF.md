# Live codec32/route review

**No codec format/route patch is justified by the reported FIFO -71 failures.** Root reports codec prepare/stop passed and SAI version23073576. These results were supplied by root, not independently measured by this agent. FIFO behavior belongs to C; this review does not change it. inputs.json and snapshot/app/k7sound freeze the read-only source used here; conclusions apply to those hashes, not future concurrent edits.

## Serial alignment

- main explicitly calls kd_prepare(...,32,...). The component writes ADC0x0c=0x10 and DAC0x17=0x20:32-bit I2S, normal polarity, separate left/right ADC data. MCLK4.096MHz/BCLK1.024MHz imply16kHz stereo64-bit frames.
- PIO sets SBW32,VDW32,SNB2,VDJ_L,EDGE_SHIFT_1, frame width64 and half-frame32. It sets XSHIFT_RIGHT=2. Official rockchip_sai_fmt_create uses exactly VDJ_L+EDGE_SHIFT_1+XSHIFT_RIGHT(2) for I2S. This is not evidence of a two-bit software sample shift; do not compensate raw words by another >>2.
- There is currently **no PCM16 conversion** in app/k7sound. Capture dump preserves uint32 words; pio_summarize converts unsigned representation to signed32 through int64 arithmetic, which avoids an out-of-range signed cast. It reports raw statistics, not calibrated audio amplitude or verified channel alignment.
- If subsequent real data confirms left-aligned signed32 samples, PCM16 is the signed interpretation of bits31:16. For example, compute uint32 hi=word>>16, then int32 pcm=hi<0x8000?hi:(int32)hi-65536, then cast to int16. This avoids implementation-defined signed right shifts. For left-aligned24-bit data padded to32, the same high16 selection applies; shifting by8 yields24-bit significance, not PCM16. Do not adopt a conversion solely from one failed frame.

After C fixes FIFO, retain raw data and inspect low-bit occupancy, both polarities, near-silence versus spoken signal, and channel ordering. A known bounded digital pattern or real clock/data observation can resolve byte/bit placement. ADC advertised internal24-bit resolution does not itself prove SAI FIFO packing. No synthetic test can replace this measurement; no format change is needed just to continue the raw32 diagnostic.

## Analog input and output

LIN2/RIN2 is supported by K7 p32 and guide pair2 example.0x0a=f0 chooses differential input for both PGAs;0x0b=82 selects pair2 with normal ADC output, not tristate.0x03=00 enables input/ADC paths,09=44 fixes PGA+12dB,12=00 and16=00 disable ALC/noise gate,10/11=00 digital0dB. Capture arm unmutes0x0f=30. Differential microphone may appear similarly in both ADC slots; do not interpret correlated channels as proof of a software duplicate. MIC is already connected; no new connection request.

OUT2 route remains coherent: DAC mixers27/2a=b8 enable DAC and disable analog bypass;04=0c enables OUT2 while OUT1 stays disabled. K7 LOUT2/ROUT2 feed AUD_LINEOUT_L/R and amplifier/SPK1/SPK2. GPIO2_B1/SPK_CTL_H is shared active-high enable. DAC1a/1b=30 and OUT2 30/31=14 retain substantial attenuation; this affects audibility, not FIFO occupancy decoding. Record/playback direction separately avoids feedback in the current diagnostic.

## 0x35 and analog baseline

Do **not** append0x35. The frozen Linux write is unchecked and exceeds its regmap maximum0x34; recovered ES8388 Rev5 describes53 registers through0x34. No source here establishes0x35 as required for this physical codec. Omission is not disproven by a PIO software -71 error after successful codec setup.

One actual baseline difference remains visible: candidate leaves06=c3 from Linux probe, while Linux's later set_bias(STANDBY) writes07=7c,05=00,06=00,02=00 and03=59. Candidate instead writes03=00 intentionally to keep both microphone ADC paths powered. Thus it is not an exact full Linux final state.06=c3 selects low-power submodes; this may affect analog performance but does not explain the software FIFO-format rejection.07/05 otherwise rely on reset defaults. No change is required to diagnose FIFO. If complete capture produces silence/noise or playback remains absent after digital checks, the smallest follow-up experiment is an explicitly recorded normal-power baseline05=00,06=00,07=7c while retaining intended03=00 and amp-muted sequencing. Do not blindly apply03=59: it powers down a different ADC path.

## Minimal follow-up

1. Preserve current codec/register choices for C's FIFO correction; no extra analog writes or gain increase to mask -71.
2. Record final clock/format register values and capture raw words after successful bounded transfer; codec_ready currently checks clock gates/divider but does not read back all TXCR/RXCR/FSCR format fields. A diagnostic readback of those fields would strengthen evidence without changing the format.
3. Verify nonzero/speech-responsive samples and raw32 alignment, then implement the small PCM16 conversion separately. A one-frame failed capture is not acceptance.
4. Only if the full digital path works but audio remains wrong, compare the documented normal-power baseline above, then gain/mute/physical output evidence. Keep each change attributable.

No code patch, test rerun, device access or audio acceptance was performed. This is a fixed-source interface/route review; prior host mocks and root's actual codec prepare/stop are separate evidence.
