# RK3576 / SAI2307 PIO reference search

**Result: no verifiable Rockchip HAL/RTOS PIO implementation or documented CPU-mode FIFO-bank selection rule was found in this bounded search.** In particular, no inspected source proves that DMACR.RDE changes CPU RXDR bank selection. This is a missing reference, not proof that such hardware behavior cannot exist. No patch or DMA-enable experiment is proposed on this evidence.

Root's latest observation is retained precisely: each62.5us group has two counted words from banks0,1,2,3 in sequence, bank0 carries data and banks1–3 carry zeros; bank0 therefore recurs every250us. RCSR=0 and DMACR=0. This review did not reproduce the trace. A bank0-only diagnostic derivative must be labeled4kHz to preserve real duration, never16kHz, and is not a fix.

## Local scope and findings

- Filename search under E:/rk3576_data for SAI/HAL/RTOS names found no matching source implementation. This does not inspect compressed SDK archives or establish that they lack one. No SDK execution area, private configuration or device was accessed; no archive was extracted.
- Filename search under E:/openvela found the already frozen Linux rockchip_sai.c/.h copies and our own candidates, no hal_sai.c or drv_sai.c reference.
- Read the existing `evidence/audio-sai-trm-20260910/SAI-layout.txt`, `SAI-application.txt` and input.json. Original PDF is E:/rk3576_data/4-HardwareData/datasheet/Rockchip_RK3576_TRM_Part1_V1.2_20240624.pdf; previously recorded SHA2566094ae5874d8494e73fa363d9cf35dd65acbd54a9a9d633b1ba5e4bea289f0a8. This round hashes the text inputs, not the full PDF anew.
- DMACR offset24: RDE bit24 and TDE bit8 are DMA-enable controls. RDL describes request threshold; TDL names the CSR-dependent FIFO used for DMA watermark comparison. Neither paragraph specifies CPU RXDR pop order, empty-bank reads, or a CPU-versus-DMA multiplexing mode.
- The application flow is explicitly DMA based (configure DMA channel to TXDR, configure DMACR, start). It is not a PIO reference. Its clear-before-configuration note is already being evaluated separately by root/C; not duplicated here.
- Frozen Linux uses 32-bit DMA addresses at RXDR/TXDR, programs request thresholds and toggles RDE/TDE. A DMA success path is not proof of CPU read-bank semantics. The `rockchip,no-dmaengine` registration branch is not itself a polling RX implementation.

## Public primary references checked

1. [Rockchip/Collabora Linux SAI source, fixed commit3364638565b6ddb797459069a64a408d6c21d6b5](https://android.googlesource.com/kernel/common/+/3364638565b6ddb797459069a64a408d6c21d6b5/sound/soc/rockchip/rockchip_sai.c). Git blob ebdf0056065b9a7ea5c271caa65d8a33666d0bd7; GPL-2.0-or-later. This is a directly browsed source revision, not HAL or RTOS; no CPU-bank rule located. Its newer version checks also make blind substitution inappropriate.
2. [Original RK3576 SAI patch series](https://lists.infradead.org/pipermail/linux-arm-kernel/2025-April/1017925.html), retrieved as search result, and [original driver patch v1](https://patchew.org/linux/20250305-rk3576-sai-v1-0-64e6cf863e9a%40collabora.com/20250305-rk3576-sai-v1-4-64e6cf863e9a%40collabora.com/). Search results identify Linux DMA integration, not a bare-metal implementation. No new HAL commit inferred from them.
3. [Rockchip official RK3576 release notes](https://github.com/rockchip-linux/rkbin/blob/master/doc/release/RK3576_EN.md) mention RT-Thread/HAL build identifiers, e.g. hal:c3f4db36 for a bus-MCU binary. This mutable release-note link is only a lead: it does not expose the relevant HAL source, establish SAI support, or constitute a full source commit we can check out. No firmware was downloaded.
4. [Manufacturer TRM public mirror](https://rockchip.fr/Rockchip%20RK3576%20TRM%20V1.2%20Part1.pdf) appeared in search, but direct web open returned Internal Error. Existing local frozen extract was used instead; no new PDF download/hash claimed.

Search terms included `Rockchip RK3576 HAL_SAI CPU FIFO DMA SAI_RDR`, `github rockchip hal_sai.c RK3576`, `"hal_sai.c" rockchip`, `"RK3576" "HAL_SAI"`, `"SAI" "CPU mode" "Rockchip"`, `"SAI_DMACR" "CPU"`, `"SAI_RXDR" "FIFO" "mode"`, GitHub/Gitee-scoped hal_sai, and RK3576 RT-Thread HAL. Results did not provide a matching original implementation. STM32 HAL_SAI, older Rockchip I2S/TDM and non-source articles were not treated as substitutes.

## Specific unresolved question for a future source or vendor answer

For version0x23073576, RCSR=0, two32-bit slots, does CPU RXDR always traverse four internal FIFOs, and if so what documented state selects/reset its pop bank? Does RDE only gate DMA requests, or also change the APB data-port bank selector? What is the expected ordering with DMA disabled? A source routine or register description answering these questions is needed before making a mode-dependent correction.

Current clear/reset/clockwait experiments may distinguish initial-state issues; their outcome cannot be predicted from this unsuccessful source search. All files written only in this new directory; no unknown code ran, no hardware/SDK operations or model access occurred.
