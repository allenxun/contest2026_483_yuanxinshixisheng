# RDE experiment: DMA precondition review

**Not yet established that no DMA channel can respond. CONFIG_DMA disabled is software build evidence only. Keep RDE experiment unstarted until the checks below are reviewed.** No MMIO or device access occurred here.

## Source-established mapping

- Frozen RK3576 DTS lines4454–4461: SAI1 base2a610000, dmas `<&dmac0 2>, <&dmac0 3>`, names tx/rx. TRM physicalpage26 request table independently lists dmac0 request3=sai1_rx. Request3 is a peripheral handshake number, **not DMA hardware channel3**. Any programmed PL330 channel can contain instructions using that request.
- DTS lines4740–4749: dmac0 `arm,pl330`, NS base2ab90000, range4000, IRQ32/33, clock ACLK_DMAC0 named apb_pclk. TRM DMAC mapping gives secure base2ab80000 and nonsecure2ab90000. Do not probe the secure alias just to bypass visibility restrictions.
- Frozen clock source: ACLK_DMAC0 parent aclk_bus_root, gate RK3576_CLKGATE_CON(19) bit1. Header clock ID201; reset symbol SRST_A_DMAC0 ID305. **ID305 is not a MMIO offset.** This review did not establish reset register/bit mapping or complete parent/security/power accessibility. No guessed clock/reset address is supplied.

## Minimal status set once accessibility is proved

Offsets relative to confirmed accessible DMAC0 window:

|Offset|Register|Meaning|
|---|---|---|
|000|DMA manager status|low4bits state; stopped0. A stopped manager alone does not prove channels stopped.|
|030 /034|manager/channel fault status|Record as faults, not substitute for idle.|
|100+8*n, n=0..7|DMA_CSRn|RO channel status; low4bits0=stopped,7=waiting peripheral,4=waiting event. Waiting states are not safe inactivity.|
|104+8*n|channel program counter|Optional diagnostic companion, not proof of harmless program. Do not dereference microcode pointers in a generic status check.|

TRM physicalpage793 CSR0 definitions independently match public [Linux v6.1 PL330 register definitions](https://raw.githubusercontent.com/torvalds/linux/v6.1/drivers/dma/pl330.c). There is no simple universal channel-enable bitmap replacing thread-state inspection: this controller executes DMA instructions. The full CSR words include security/state fields; preserve them rather than only printing a derived idle boolean. Request number is not directly determined from one CSR low nibble.

## Read-only review procedure and stop conditions

1. Confirm address map, MMU/device memory attributes, DMAC0 bus access/security rights and existing ACLK/parent/reset state from already available platform records. Do not touch inaccessible DMAC registers to discover whether clocks are off: such reads can fault or stall. If clock/reset state is unknown or requires enabling/deasserting writes, stop this read-only check and keep RDE off. Clock-gated does not mean unconfigured; retained state may resume later.
2. Establish whether the current nonsecure view exposes all channels, including any secure channel using request3. If secure ownership/visibility cannot be established from trusted boot/platform evidence, zero NS reads cannot certify absence. Do not treat CONFIG_DMA=n or all-zero/unimplemented reads as a hardware reset proof.
3. Under exclusive software ownership, record accessible manager/full8-channel states and faults, with timestamps, twice. All stopped is a bounded snapshot, not perpetual proof. Any WFP/WFE/running/transitional/fault state fails the experiment precondition; do not infer that unrelated source/destination addresses make it harmless.
4. Establish no CPU/firmware/secure owner can start or resume a channel during the RDE window. Keep the same ownership until RDE is verified off and SAI stopped. Status snapshots without this guarantee do not close the race.
5. No writes to DBGCMD/DBGINST/INTCLR/reset/clock/DMA engine are part of the proposed check. Do not kill unknown channels to make the experiment pass. If accessibility or ownership remains unproven, continue only the independent ADC gain test.

Original TRM source: E:/rk3576_data/4-HardwareData/datasheet/Rockchip_RK3576_TRM_Part1_V1.2_20240624.pdf, prior frozen SHA2566094ae5874d8494e73fa363d9cf35dd65acbd54a9a9d633b1ba5e4bea289f0a8 (not rehashed here). New local text extractions identify physicalpage numbers; paths/hashes of source DTS/clock/header in inputs.json. No SDK runtime, device, private config, original-source or central-log writes. No full DMA driver developed.
