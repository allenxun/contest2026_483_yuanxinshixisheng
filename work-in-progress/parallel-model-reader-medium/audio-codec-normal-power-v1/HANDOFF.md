# Normal-power codec comparison

Root reports FIFO transfer now succeeds for3200/48000 capture frames but all samples are zero; tone3200 frames also transfers successfully. This agent did not observe hardware or audible output. The patch is a controlled analog-power comparison, **not a claimed all-zero fix**.

The source is frozen from current app/k7sound codec_duplex.c/.h in input-codec_duplex.*; frozen-inputs.json is authoritative for that baseline. normal-power.patch changes one initializer line only: replace06=c3 with Linux set_bias(STANDBY) order07=7c,05=00,06=00. Named-field verification masks are7f/e8/c3 respectively. Later03=00 remains untouched so both ADC/input paths stay enabled. The original standalone component's APIs, slot selection, delays, gain, mute, stop and amplifier policy are unchanged.

Candidate codec_duplex.c SHA256:82906169d9285611ce9b2de0361347cc518cfba0620de78cd8b63ca86e9c0bee.

Official frozen Linux es8323_set_bias_level(STANDBY) writes ANAVOLMANAG7c, CHIPLOPOW1/2 zero, CHIPPOWER00, ADCPOWER59. Only the normal-power subset is adopted.03=59 disables a different set of input/ADC blocks; copying it would confound the LIN2/RIN2 dual-ADC diagnostic. No0x35 is added. ADC/DAC digital release02=00 already exists later in the candidate.

## Readback diagnostic points

Take a bounded same-owner snapshot **after prepare**, then again in the prestart hook **after kd_arm** while TX/RX FIFOs are stopped and CLK/FS runs. Store results in a small RAM array and print only after the transfer/stop. Do not perform I2C or serial printing in the PIO service loop. Do not use post-stop power/mute values as evidence of active capture configuration. On read error, record errno and abort/recover instead of printing a fabricated zero.

| Registers | After prepare / capture-arm expectation | Interpretation |
| --- | --- | --- |
|00|36|SameFs=1 and DACMCLK selection bit5=1 retained from Linux; compare raw byte for diagnosis, not unreviewed reserved/reset bits as a blanket gate.|
|01|60|Linux analog baseline unchanged; raw diagnostic only.|
|02|00|Both digital domains/state machines/references released. Anyf3/f0 still present would indicate stopped/partial state.|
|03|00|Both inputs/ADCs enabled. fc/ff means powered down.|
|04|0c|DAC channels/OUT2 configuration, unchanged; no need to turn DAC off for this capture-only experiment.|
|05,06,07|00,00,7c|New normal-power comparison.|
|08|00 **all8 bits**|MSC=0 slave; MCLKDIV2=0; BCLK inversion=0; BCLKDIV[4:0]=0. Previous prepare mask e0 does not check the low divider bits.|
|2b|80|Shared LRCK enabled; bit6=0 per guide. Inspect other bits for unintended clock disables.|
|09,0a,0b|44,f0,82|+12dB fixed PGA, differential both channels, LIN2/RIN2, no tristate.|
|0c,0d|10,02|32-bit I2S separate ADC data and256 ratio.|
|0f|34 /30|Muted after prepare; capture arm must clear bit2.|
|10,11,12,16|00,00,00,00|ADC digital volume0dB, ALC/noise gate disabled.|
|17,18,19|20,02,06|DAC32-bit/ratio; capture-only arm keeps DAC muted. Playback arm changes19 to02.|

This table is a diagnostic expected-value list, not a universal readable-bit whitelist. It targets registers already used in this component plus the defined clock/power controls. Return real bytes and note the lifecycle point. Existing stable-field checks still fail on mismatch. Reserved/self-resetting fields should not be added to strict masks without evidence.

## Why clocks could produce zero — and what is currently correct

Guide §5.1/5.2 says0x08 bit7 selects master/slave; slave mode expects external SCLK/LRCK and BCLKDIV=0. Current08=00 is correct for SAI master; setting80 would create competing clock masters, not repair missing samples. MCLKDIV2 would alter the effective ratio, and stale lower divider/clock-control state warrants readback. Actual pin clocks are not proven by MMIO configuration alone.

Guide also requires register43(0x2b) bit6=0 and selects shared ADC/DAC LRCK with bit7. Current80 fits that reference.00=36 uses the Linux same-frequency/DAC-clock-source arrangement. Since this candidate leaves both digital domains released02=00 and DAC channels powered04=0c, there is no demonstrated need to switch it to ADC-clock-source solely because PIO is receiving. If a future capture-only optimization powers down the DAC domain while retaining its clock selection, that dependency must be reviewed; do not make that optimization during this comparison.

Exact zero can reflect ADC mute/power/reset, clock delivery, tristated ASDOUT/input pin routing or a receive-path problem. A low microphone level normally does not by itself establish exact digital zeros across three seconds. The present evidence does not identify which cause applies. Normal-power06=00 may change analog behavior, but low-power configuration is not proven responsible.

## Minimal next run

1. Integrate only this initializer change after matching baseline hash; rebuild through root's normal process.
2. Prepare + prestart-after-arm readback snapshot, amp low for capture. Preserve full register values/errors and actual timing stage.
3. Repeat the same bounded raw32 capture/profile/gain; compare zero/nonzero and signed ranges. If still zero with coherent readbacks, retain this result and investigate physical clock/ASDOUT delivery rather than increasing gain or adding0x35.
4. Keep playback listening evidence distinct from successful FIFO counts. No claim of acoustic success follows from result0 alone.

## Host evidence

Real C component tests pass at O0/O2 with524 checks each, including explicit05/06/07 final values and03 remaining00, all prepare/activate/stop callback faults, mismatch/timeouts and cleanup. Mock registers only; no analog simulation. results.json contains commands/stdout (compile30s, execution15s). Header copied unchanged; no hardware/SDK/formal/central-log modifications by this agent. prepare.py regenerates within this directory, so do not rerun it after root integrates a new baseline without intentionally versioning the input.
