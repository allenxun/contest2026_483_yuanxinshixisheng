# Duplex v2: PIO hook contract and attenuation

This independently derives from frozen audio-codec-duplex-v1. Register initialization, readback masks and volumes remain unchanged; see its HANDOFF for sources. No other agent/formal/SDK/device files changed. This version adds a deferred amplifier-enable option so the PIO service loop does not spend30ms inside codec activation.

## Correct prestart contract

Root's proposed CLK/FS-running, TXS/RXS-disabled window is practical **if the SAI hardware really does not consume/fill FIFOs until TXS/RXS is enabled**. In that window ready reports actual MCLK/BCLK/LRCK/format and configured/stopped directions, not already-running data streams. Source pio.c currently enables CLK/FSS separately from TXS/RXS, so there is a concrete insertion point. Hardware behavior remains C/root verification.

The previous ready wording requiring running streams was too strong for this synchronous PIO layout; it is replaced in the v2 header. Do not assert running when merely configured. For prepare's ready(false,false), verify the same clocks/profile without a data-stream requirement. If prepare occurs before CLK/FS exists, run it inside the prestart hook after CLK/FS enable instead of falsely confirming clocks.

Recommended hooks in pio_run, **not implemented in another agent's file**:

1. Existing configure/clear/status checks, zero-prefill TX FIFO while TXS=0. Enable CLK/FSS, retain TXS/RXS=0.
2. `before_start` hook: if needed kd_prepare(c,32,deadline), then kd_arm(c,!tx,tx,deadline). kd_arm performs unmute and30ms playback wait, leaving amplifier LOW. All lengthy I2C/delays occur here while the data FIFO is disabled. ADC serial data may already be produced but is deliberately not captured yet.
3. Enable the selected TXS/RXS bit, then immediate `after_start` hook for playback: kd_enable_amp(c,deadline). It performs only the bounded amp GPIO callback and clock bookkeeping: no I2C/readback/wait.
4. Start the sample-duration timer **after the prestart hook**, at stream start. Enter the tight service loop immediately. No logging, codec I2C or sleeping in this loop.
5. On hook/start/poll failure, preserve error and ownership, disable amplifier and perform PIO cleanup plus kd_stop. Root quiesce must understand whether PIO already stopped; do not recursively enter pio_run from a hook. If PIO cleanup failed/held, retain that status until supervisor recovery.

Zero-prefill more than one stereo frame: a single frame lasts only62.5us at16kHz. Example16 stereo frames/32 FIFO words gives1ms before depletion, subject to actual FIFO capacity and consumption semantics. The GPIO poststart callback must finish substantially inside the available FIFO runway; its deadline must not be a millisecond-scale sleep. Count prefilled frames in total-frame accounting. C/root chooses a measured suitable prefill and service bound; this agent does not claim the original one-frame prefill is adequate.

The original kd_activate remains available and enables amplifier before it returns. Calling it in a single prestart hook can also work if disabled-TX SDO is guaranteed zero, but it exposes a stale-data/pop interval before TX start. The deferred two-hook form avoids that interval without requiring a second thread. kd_arm success sets amp_armed only for playback; kd_enable_amp is one-shot, rejects capture-only and clears the latch on mute/stop/error. It does not independently inspect SAI: caller is responsible for actual successful TX start and prefill. KD_ACTIVE describes codec state, not proof that PIO is running.

## First tone amplitude

For signed32 peak full scale2^31, ±2^20 is −66.23dBFS peak. Codec digital−24dB and OUT2−15dB yield about−105.23dB relative to that reference before external amplifier gain: likely unsuitable as an audibility test. ±2^27 is −24.08dBFS peak; unchanged codec gain gives about−63.08dB. A square wave's RMS equals its peak magnitude; a sine with the same peak has3.01dB lower RMS. These are linear signal-level estimates, **not SPL, amplifier watts, or guaranteed audibility**.

Use ±2^27 as the first short250Hz tone (e.g. existing200ms window), followed by silence/amp-disable. If output is verified but too quiet, root can prepare a separately recorded gain change between tones:

| DAC1a/1b code | DAC attenuation | OUT2 code | Combined with ±2^27 |
| --- | --- | --- | --- |
|30|−24dB|14 (−15dB)|−63.08dB|
|24|−18dB|14|−57.08dB|
|18|−12dB|14|−51.08dB|
|0c|−6dB|14|−45.08dB|

Do not automatically ramp through these levels or write registers from a competing owner. v2 keeps the first row; there is no live-volume API. A gain change should occur under the same owner while muted/stopped, with readback and trace. Actual microphone/speaker/amp gain and load are still unmeasured; lack of sound should first trigger clock/data/routing/mute checks, not repeated gain increases. Raw32 data alignment still needs C/root verification before using these numerical estimates.

## Evidence

Unchanged baseline tests plus deferred-arm tests pass at O0/O2,492 checks each. Tests confirm amp stays low through arm, enable_amp makes exactly one device callback without delay/time advance in the mock, repeated/capture-only enable is rejected, and timeout/GPIO failure clears the arm latch and permits explicit cleanup retry. These are real C component tests with mocked hardware; no FIFO service timing or audibility was tested.

run_tests.py retains30s compile/15s executable limits and exact commands/stdout in results.json. v2 inputs additionally freeze the old component and reviewed C-agent pio.c/.h by hash. Changes to C's PIO hooks remain root/C work. No hardware execution or acceptance claim.
