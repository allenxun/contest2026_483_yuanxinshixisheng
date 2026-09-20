# Reference-startup versus current codec state

**The decoded differences do not establish an ADC-disabled/DAC-enabled fault in the current36/60/00 settings.** Do not change the loaded normal-power version while collecting its readbacks and GPIO observations. This is a read-only review with bit-arithmetic checks, not another register experiment or hardware result.

Definitions were rechecked against the manufacturer-branded [ES8388 Rev5.0 July2018 datasheet, pp13–14](https://manuals.plus/m/bd624af22c64cb927c8e43b74e90e0cf87e67ead91628d6361e035bb06eda94d.pdf). Its web-readable PDF is a third-party mirror; no downloaded PDF hash is claimed. Local guide is the previously frozen Radxa2011-06-17 PDF, p20. Do not confuse decimal register headings with hexadecimal addresses.

| Register/field | Guide | Current | Meaning |
| --- | --- | --- | --- |
|00 reset7/LRCM6/SeqEn3|0/0/0|0/0/0|Same state.|
|00 EnRef2|1|1|Reference enabled in both.|
|00 VMIDSEL1:0|01|10|50kΩ versus500kΩ divider.|
|00 SameFs4/DACMCLK5|0/0|1/1|Separate Fs control versus shared Fs with DAC clock source.|
|01 LPVcmMod5|0|1|Normal versus low-power common-mode setting.|
|01 named shutdown bits3/2/0|0/0/0|0/0/0|Analog, bias generator and reference buffer not shut down.|
|01 bit6|1|1|Not explained in inspected named-field table; not a difference.|
|02 ADC bits7/5/3/1|all0|all0|ADC digital/state/DLL/reference enabled.|
|02 DAC bits6/4/2/0|all1|all0|Guide recording example disables DAC domain; current leaves it enabled.|

Other named01 low-power bits4/1 are zero in both. The table describes documented control intent, not actual internal clocks or voltages. The VMID/common-mode differences can affect bias behavior or settling, but the document does not prove they cause three seconds of exact zero data.

## MICBIAS and shared clock dependencies

MICBIAS is03 bit3, not the differing00/01 fields. Both capture configurations use03=00, so its control is enabled;03 also enables both input/ADC paths. The K7 microphone external resistor bias network is separate from assuming an on-chip bias output supplies the connector. Register readback does not measure bias voltage.

Guide02=55 must be interpreted together with its00=05. Copying only55 into the current00=36 state would shut down the selected DAC clock domain while retaining shared-DAC-clock selection. It could create a new dependency problem. Current02=00 and04=0c leave DAC circuitry available, so there is no demonstrated disabled source in the present configuration.08=00 remains appropriate slave mode; do not switch to codec master as a zero-data workaround.2b=80/shared LRCK remains a separate check.

## Conditional next decision

- First use the running version's actual after-arm register snapshot: ADC-control02&aa must be0,03 input/ADC shutdown bits must be0,0f mute bit2 must be0,0b tristate bit2 must be0, and08/2b must match the intended external-clock configuration. A mismatch takes priority over speculative baseline changes.
- GPIO4_B3 transitions with all-zero FIFO data would shift attention toward sampling/data interpretation. No transitions during4096 asynchronous reads is inconclusive: short-window aliasing, pad-input visibility, clock delivery, tristate/pull state and true zero data remain distinguishable possibilities. Record sampling duration/rate and lifecycle point; do not claim a codec output waveform from GPIO counts alone.
- If coherent clocks/readbacks still leave zero data, the smallest documented normal-common-mode comparison is01:60→40, changing onlybit5. Keep all other settings fixed.
- A separate reference-bias comparison is00:36→35, changing VMID divider500kΩ→50kΩ while preserving SameFs/DAC clock selection. Record settling and result; no universal new delay is established here.
- A full guide recording-mode comparison00=05/01=40/02=55 is a later coupled experiment, capture-only with output disabled and normal teardown. It is not the first minimal change and must not be mixed with an attempt to assess DAC playback.

No patch is supplied. The alternatives are conditional engineering comparisons, not proven fixes. Root remains owner of when/if to perform them. Existing exact-zero capture and successful transfer reports are preserved without elevating them to microphone acceptance.

inputs.json freezes the current codec and source references; input-codec_duplex.* is the exact read-only snapshot. decode-checks.json verifies the small mask comparisons only. No SDK/device/formal/central-log writes or extra agents.
