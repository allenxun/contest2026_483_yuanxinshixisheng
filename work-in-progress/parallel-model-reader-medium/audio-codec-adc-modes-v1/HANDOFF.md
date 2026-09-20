# Explicit ADC comparison modes

Root reports normal-power capture3200 returned0 with all-zero data, GPIO4B3 sampled4096 times low, and after-arm0f=20 after writing30. These are supplied live observations, not measurements repeated by this agent.

## 0f=20 does not mean mute

The [manufacturer ES8388 Rev5 §6.2.7 p19](https://manuals.plus/m/bd624af22c64cb927c8e43b74e90e0cf87e67ead91628d6361e035bb06eda94d.pdf) defines0x0f bits7:6 ramp rate,5 soft ramp,3 linked gain and2 ADC mute; bit4 is not defined there. Default is20.30→20 clears onlybit4; mute remains0 and soft ramp remains1. This is consistent with an undefined/reserved bit reading zero, but no universal reserved-bit read contract is claimed. Keep the mute comparison mask04. Do not repeatedly forcebit4 or broaden the check toff.

That observation does **not** identify an ES8323 replacement, prove genuine ES8388 silicon, or establish a compatibility defect. Board schematic/DTS name ES8388 with Linux es8323 compatibility; actual lot/revision is still not established by I2C ACK or this readback. No chip-ID register or identity guess is introduced. The candidate retains existing mute writes to keep the new tests single-variable.

## One firmware, three explicit modes

New API `kd_prepare_adc_variant(c,32,variant,deadline)`; original kd_prepare remains a baseline wrapper. All begin only in KD_OFF and execute the full reset/init sequence. No hot switching, automatic fallback, combined experiment or hidden retry.

| enum | Suggested CLI name |00|01|Purpose|
| --- | --- | --- | --- | --- |
|KD_ADC_BASELINE|baseline|36|60|Current normal-power baseline.|
|KD_ADC_COMMON_NORMAL|common|36|40|Clear common-mode low-power bit5 only.|
|KD_ADC_VMID_50K|vmid50k|35|60|VMID500kΩ→50kΩ only; retain shared DAC clock source.|

All modes retain02=00,03=00,05/06=00,07=7c,08=00,LIN2/RIN2 f0/82,32-bit format,ALC/noise gate off,fixed gain and mute/amp handling. The changed field is readback-compared:common01 mask20;vmid00 mask03. Reset00=80→00 is unchanged. ADC/DAC clock-domain arrangement is intentionally preserved; no02=55 or codec-master switch.

## Root integration

Add an explicit mode argument only to capture/probe, resolve it to the enum before taking hardware ownership, and print the chosen enum/name. Keep default baseline. In main replace the prepare call with kd_prepare_adc_variant. Do not modify codec registers out-of-band after prepare.

For **every** mode, including baseline, root may perform the requested bounded1000ms wait after prepare success with amplifier LOW, retained MCLK/rails, and TX/RX not yet started. Use the same wait in all comparisons and record actual elapsed time. This is an engineering settling window, not a manufacturer-certified sufficient delay. The existing3000ms prepare deadline need not include a later wait; root must maintain an overall command bound and use fresh arm/capture deadlines. If the wait fails or is cancelled, stop/cleanup; never proceed with an uncertain owner.

Then take after-arm register snapshot in the prestart window, start the same bounded capture and retain raw sample/nonzero/min/max plus pad high/transition counts with time window. Each mode must finish successful kd_stop and root platform/I2C cleanup before the next mode's complete reset. Failure retains ownership; no automatic attempt of another mode.

Root plans to change SDI0 pad bias from pulldown to official pull-none in the next image. **That is a separate baseline change** outside this candidate. First run baseline mode with pull-none, then common/vmid using that same image, wait and pad state. Do not attribute a changed result directly to reference bias by comparing an old pulldown run only against a new reference-mode run. This agent has not independently validated A's pad finding or changed pinmux.

A lower VMID resistance plausibly changes bias charging/settling; the documents do not prove it causes the observed zero stream or that one second resolves it. With correct register values and continued zero pad samples, distinguish actual clock/data visibility from analog level before escalating gains. GPIO sample counts remain limited asynchronous observations.

## Delivery/tests

input-codec_duplex.c/.h freeze formal normal-power files. adc-modes.patch is the minimal API/initializer-selection difference. No formal/device/SDK/log files changed. fixed-inputs.json captures these baseline bytes and cited source hashes; inputs.json from the inherited harness lists other frozen references.

O0/O2 strict C11 builds each pass1309 host checks: existing lifecycle/fault tests plus independent mode register equivalence, changed-field verification paths, every mode-prepare callback failure, invalid mode no-I/O and live-mode rejection. Fake register final state differs only in00 or01 as selected. No real ADC, delay settling or audio result is simulated or accepted. results.json includes argv/stdout with30s compile/15s execution limits.
