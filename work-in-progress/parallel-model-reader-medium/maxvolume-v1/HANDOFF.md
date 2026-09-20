# Maximum legal codec playback volume

User requested maximum speaker volume; root retains board ownership. `kd_set_playback_max(c,deadline)` is an additive prepared-only interface layered on frozen gain-v1. It first calls amp(false), which must drive LOW and verify physical GPIO readback, then writes/readbacks1a=00,1b=00,30=21,31=21. DAC masks ff, OUT2 masks3f (documented volume field; reserved upper bits not compared). No activation/unmute, no amplifier circuit change, no PCM normalization, no zero removal. Default init unchanged.

## Verified values and provenance

Frozen official SDK `parallel-k7-audio/sources/kernel-6.1/sound/soc/codecs/es8323.c` line175 declares out_tlv base-4500 hundredths dB, step150; lines214–215 specify Output2 max33 without inversion. Header lines64–65 maps DACCONTROL26/27 to0x30/0x31. Thus maximum is33 decimal=0x21, -45+33*1.5=+4.5dB. It is not0x3f. DAC inverted volume control at lines174/206–207 supports code00=0dB.

Frozen manufacturer ES8388 user guide2011-06-17 text line1297 confirms output range-45 to+4.5dB,1.5dB steps; the following line notes above0dB can clip large signals. Local original PDF provenance: https://dl.radxa.com/rock2/docs/hw/ds/ES8388%20user%20Guide.pdf , SHA2566d25413e840d096186b21f9aa1eff8b58b95ea97d216a248c60ea178884d0457. This round hashes frozen text and SDK source/header; no new download. Numeric mapping is source-verified, not remembered.

Combined configured gain changes from default DAC-24/OUT2-15=-39dB to DAC0/OUT2+4.5=+4.5dB, an increase43.5dB. This is codec configuration gain, not measured SPL/power; amplifier part/load remain outside this interface. It does not make every PCM clip or full scale, and it does not fix FIFO bank behavior.

## Failure/lifecycle

Only KD_PREPARED/nonbusy accepted. Wrong state/null reject without I/O; accepted timeout or callback/readback error enters KD_FAULT, clears amp_armed, and forbids later kd_arm. Error after partial register updates leaves partial settings but never enables amplifier. Bounded best-effort amp(false) is repeated if time remains. A failed GPIO callback cannot guarantee physical LOW; caller must recover. Stop/reprepare required before retry. Source callback execution cannot be preempted by this synchronous API.

Root integration: successfulprepare → set_playback_max → normalarm/start/enable_amp → normalstop. Do not call gain-v1 after maximum expecting OUT2 default: gain-v1 intentionally only changes DAC. For baseline comparisons use a freshprepare. Patch is relative to frozen gain-v1, which must be integrated first; candidate complete.c/.h already includes both additions.

Tests use fake GPIO/I2C only: O0/O2 original lifecycle, gain regression, all9 max-operation callback faults/timeouts, all4 register mismatches, exact256-byte delta, bad state/busy/null/deadline, and nonactivation on failure. No board operations or formal changes. Source inputs and results are hashed in delivery.json.
