# ES8388 record/playback engineering candidate

This is an executable C11 codec configuration component for root's real I2C/SAI/GPIO adapters. It does not return unconditional NOT_READY and does not change the old kc_plan review flags. It is a separate synchronous sequencer: **use one owner, never run it alongside codec_txn on the same codec**. No dynamic allocation, device/SDK access or formal changes were made here. Target build, ACK/readback, PCM and audible output remain root verification.

## Interface and integration

1. Static kd_codec + kd_port; kd_bind once before use (never reinitialize a live owner). Call everything from one serialized task. busy rejects callback reentry, not concurrent SMP access.
2. kd_prepare(codec,32,deadline) is preferred for the first raw32 probe;16 is also accepted. It first disables the amp, calls ready(false,false) to verify powered rails and the actual clock/profile, resets/configures the codec, compares selected stable fields, and leaves both digital channels muted and amplifier off in KD_PREPARED. Start zero-fed TX/RX under root's SAI ownership before activation.
3. kd_activate(c,capture,playback,deadline) first disables amp, asks ready to confirm requested streams/clocks, unmutes the requested direction, and only for playback waits30ms before amp(true). At least one direction required. It can also resume after kd_mute or change requested directions; ready must own/reconcile actual stream state.
4. kd_mute disables amp then mutes DAC/ADC; resources remain owned. kd_stop disables amp, mutes, confirms quiesce, resets digital/analog/DAC output state, waits40ms and returns KD_OFF. Clocks remain available: root disables clocks only after successful stop. quiesce must join all old PIO/DMA work, not just send cancel.
5. Any failure produces KD_FAULT and retains ownership. Give kd_stop a fresh bounded deadline, fix the failed lower layer, and retry; only successful stop permits another prepare. Do not drop or memset the context to bypass cleanup. Activation has best-effort amp-disable on error, but **fault does not prove physical mute** when GPIO/I2C itself failed. Root must recover/disable the amplifier independently if needed.

Callbacks return0 only after actual completion; negative errno otherwise. write performs TX2 [register,value]; read performs combined/repeated-start TX1+RX1, checking each actual transfer length in the adapter. Never pass an8-bit shifted address: component passes7-bit0x10. read values must come from hardware, not shadow/regmap defaults. Adapters enforce controller deadlines, STOP and buffer-lifetime completion. The core detects late return/early delay/clock rollback but cannot interrupt a stuck synchronous callback. Cross-thread cancellation must queue to the owner; no preemptive cancellation API is supplied.

## Format

| Fs / stereo word and slot width | MCLK | BCLK | ADC0x0c | DAC0x17 |
| --- | --- | --- | --- | --- |
|16k /16-bit|4.096MHz|512kHz|0x0c|0x18|
|16k /32-bit|4.096MHz|1.024MHz|0x10|0x20|

Both use I2S one-bit delay, normal polarity, codec slave, ADC data selector0 (left ADC/left slot, right ADC/right slot), ADC/DAC rate0x0d/0x18=0x02. The Linux hw_params explicitly contains S32 values even though its advertised formats omit S32; manufacturer word-length definitions support the choice, but raw32 capture still needs actual wire verification. Do not merely widen SAI slots while keeping codec16-bit. Do not assume raw32 memory packing or signed PCM alignment: root/C first inspect raw words, then choose sign extension/shift/saturation conversion. This component does not read/write SAI FIFO.

## Initialization decisions and provenance

inputs.json freezes Linux codec/header, board DTS, multicodecs GPIO timing, manufacturer guide and schematic extracts. init[] is the exact ordered candidate; review it directly rather than relying on an unordered register map.

| Group | Choice and source |
| --- | --- |
| Reset/common power | Linux es8323_reset 00=80→00; probe baseline01=60,02=f3→f0,2b=80,00=36,08=00,06=c3 retained. This resolves guide versus Linux common-power differences in favor of deployed board-family Linux. Unexplained/reserved common bits are not readback-compared. |
| Clock source | Linux same-clock configuration retained; final02=00 enables both digital domains. Explicitly fixed4.096MHz, not the DTS boot12.288MHz. ready must check actual output; Linux coeff_div supports4096000/16000. |
| MIC | Guide pair2 example0a=f0/0b=82;09=44 selects fixed+12dB PGA.12=00 disables ALC and16=00 disables noise gate, avoiding conflicting guide ALC samples and inherited automatic gain. This is a starting gain, not calibrated sensitivity. Both ADC channels remain available for inspection. |
| ADC format/volume | Derived16/32-bit values above;10/11=00 digital0dB;0f=34 muted until activation, then30. |
| DAC/mixers | Linux17 S16/S32,18 rate,27/2a=b8 enable DAC-to-output with bypass off;26=00 explicit mixer input baseline.19=06 muted (Linux suspend),02 unmuted (Linux probe/resume). |
| Low output |1a/1b=30 is DAC−24dB (0.5dB/code).30/31=14 is OUT2−15dB (−45dB+1.5dB/code), approximately−39dB combined before external amplifier. No user-supplied volume API in this first bounded component. |
| Output power |04=c0 during setup, then0c enables OUT2 only. OUT1 stays disabled;2e/2f=00. Linux resume uses04=0c. Exclude out-of-range0x35 and loud probe output values. |
| Delays |20ms at the two analogous Linux probe settling points (Linux18–20ms). This preserves a concrete engineering timing baseline, not a guarantee over all cold rails/parts. Amp30ms enable/40ms disable policy comes from board DTS and mc_spk_event. |
| Stop | Guide mute/reset/ADC powerdown/DAC disable sequence combined with required joined stream teardown. Do not copy Linux suspend's clock/cache-only assumptions into raw I2C. |

The guide's0x0c=40/comment00 conflict is explicitly resolved to separate ADC data. ALC sample0x13=a0/commentc0 is avoided by ALC off.0x01=60 and06=c3 remain Linux full-byte choices with undocumented-bit limitations; this candidate does not invent semantics for those bits. If target readback or recording fails, preserve that evidence and adjust a new version, not silently relax checks.

## Mask policy

Only selected stable fields are compared after their write; no read-modify-write and no whole-map dump. Masks in init[]:08:e0;09:ff;0a:f0;0b:9c;0c:ff;0d:3f;0f:04;10/11:ff;12:c0;16:01;17:7e;18:3f;19:04;1a/1b:ff;27/2a:c0;30/31:3f;04:fc. Derived from named format/mute/selector/volume/power fields in the manufacturer definitions and Linux controls. Reset, common analog/power and undocumented fields are not verified. This explicit hardware-read policy is an engineering integration choice, not prior real-board validation or automatic TARGET_REVIEWED promotion. A mismatching compared bit fails rather than being ignored.

## Amplifier and speaker routing

Board DTS spk-con-gpio=&gpio2 RK_PB1 GPIO_ACTIVE_HIGH; schematic SPK_CTL_H drives both amplifier EN pins with pulldown. amp(false)=GPIO2_B1 low, amp(true)=high after the requested delay. Root supplies actual pinmux/GPIO driver. Both channels share enable; selecting one speaker is by sample data, not separate EN GPIOs.

Codec LOUT2/ROUT2 feed AUD_LINEOUT_L/R, then the external amplifier pair and SPK1/SPK2 respectively in the schematic. SPK1 J7400 pin1=N/pin2=P; SPK2 J7401 likewise. These are differential amplified outputs, neither negative terminal is ground. Actual amplifier variant/load/gain are not measured by this agent, so the attenuation is a conservative starting level, not a guaranteed sound-pressure or speaker-power bound. Begin with zero samples and a small digitally bounded waveform; root decides the physical test. MIC already connected is accepted.

## Host evidence and remaining validation

run_tests.py: GCC12 C11 strict warnings O0/O2 each473 checks pass. Tests exercise both profiles, mute/resume/capture-only, every prepare/activate callback fault and every stop callback fault, wrong readback, early delay, late return/deadline, callback reentry and cleanup retry. Fake I2C registers/GPIO/clock/quiescence are explicitly mocks; no PCM samples or amplifier electronics are simulated. First compile's test indentation warning is preserved in attempt-01.json and fixed without disabling warnings. results.json contains exact commands/output and30s compile/15s execution limits.

Root next: target compile → bounded I2C transactions/readback with amp low → clock/profile verification → raw32 finite capture and low-amplitude playback → stop/amp-low/quiescence evidence. Record actual callback error, stage and register via root tracing (core retains error/state only). Successful preparation proves only returned callbacks/readback, not correct audio. No further model/TTS work is required to test this component.
