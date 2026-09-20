# Capture-only SAI receive-request probe

User's latest listening correction is retained: maximum-volume speech required careful listening and has noise; it is not clear/usable recording acceptance. The request-mode hypothesis is unproven. This candidate performs no hardware or DMA-engine operations and must remain separate from root's PGA24 experiment.

## API and integration

`pio_run_rx_request(port, prepared, actual_mclk, capture, capacity_words, frames, result, request_report)` wraps the unchanged original pio_run capture path. All original pio.c bytes are retained as the prefix; pio_run, pio_play_buffer, pio_run_clockwait, run and stop are not edited. The only header addition is a separate report and new function declaration; pio_result layout is unchanged.

The adapter intercepts the original RXS-start write, reads all8 slot masks without changing them, checks DMACR RDE/TDE remain0, sets only RDE, verifies the complete expected DMACR, then allows original RXS start. RDL and all other DMACR bits retain their read values. No mask/CSR experiment or DMA channel configuration/submission is added; the original normal-format CSR write remains unchanged. Only SAI-local offsets are accessed. Existing32-word trace init[4] captures enabled DMACR; report stores initial/enabled/final values with rc validity and8 masks/rc.

On normal/error cleanup, original amp-off runs first. Before original stop's first RXS-clear write, adapter clears RDE and reads it back, also requiring TDE0. Clear/readback failure returns error to stop, leaving held1 and prohibiting platform restore. If stop's preceding XFER read fails before reaching the adapter, post-return fallback still attempts RDE clear/readback and keeps held1 because original stop did not complete. No subsequent platform cleanup is permitted merely because fallback cleared RDE. Root owns explicit recovery of held resources.

Early rejection (bad args/version/active stream or pre-existing RDE/TDE) never takes ownership or clears somebody else's request. Every path that **attempted experimental enable** attempts disable, including a write that returned failure after hardware side effects. Report flags distinguish not-entered phases; unobserved values have rc=-38. Mask read failures invalidate only that diagnostic field, like existing trace diagnostics; no fabricated value. Initial/enabled/final snapshots are sequential, not atomic.

## Required boundary and risk

The caller must exclusively own SAI and establish that no DMA engine channel is configured to respond to its RX request. Merely not submitting DMA in this function is not sufficient proof about an already configured engine elsewhere. The candidate does not inspect or alter DMA engine registers. It only exposes SAI request signaling, which could be visible to another configured channel if caller ownership is false. No automatic board execution is authorized by this artifact.

RDE request assertion may change nothing, may alter request behavior, or expose unsupported CPU-path interactions. Do not label enabling it a FIFO repair. Preserve raw frame count/zero samples/timestamps and compare only one variable against default; do not combine PGA, gain, clockwait/reset or slot-mask changes. More diagnostic reads perturb timing. MMIO/time callbacks must remain ordered, nonblocking and bounded; synchronous calls cannot forcibly interrupt a hung backend.

## Host evidence

O0/O2 strict C11 build and runs in results.json, each compile30s/run15s limit. Existing trace and playback regressions run first unchanged. Additional mock tests verify RDE enable before RXS, full expected enable readback, RDL preservation/TDE never enabled,8 mask reads/no writes, full trace, partial enable-write error cleanup, enable/read/clear/final-read errors, stuck enabled bit retains held, failed stop pre-read triggers fallback/held, stream hook and RXDR failures, pre-existing RDE/TDE rejection and bad capacity. Mock FIFO behavior is a synthetic test fixture, not silicon evidence.

First sealing check caught newline normalization by patch application after both binaries passed; original bytes were restored before final manifest. No compiler warning was disabled. Inputs include exact formal pio.c/h and official header snapshot. Current main/codec files were not touched. `request.patch` adds only the new interface and adapter.
