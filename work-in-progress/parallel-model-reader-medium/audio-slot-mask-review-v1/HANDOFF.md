# SAI2307 slot masks and data counters

**No documented missing slot-mask initialization or DATA_CNT configuration has been identified.** MASK0–3 are successive ranges of slot numbers, not individual FIFO-bank enables. Their reset value0 means active, not disabled. A real readback of all masks is still required to exclude inherited nonzero values; reset defaults are not measurements.

| Register | Offset | TRM meaning | Reset |
|---|---|---|---|
|TX_SLOT_MASK0–3|3c/40/44/48|RW slot0–31,32–63,64–95,96–127 respectively; each bit value0=active, value1=masked/data invalid|each00000000|
|RX_SLOT_MASK0–3|4c/50/54/58|same slot ranges and polarity for receive|each00000000|
|TX_DATA_CNT|5c|RO32-bit Tx data counter|00000000|
|RX_DATA_CNT|60|RO32-bit Rx data counter|00000000|
|XFER[4]/[5]|10|TX/RX counter start1, stop0|both0|

The counter is not a requested number of slots. Do not write2 into DATA_CNT. The inspected TRM description does not specify enough detail to equate counter units with frames, words per lane or APB reads, nor establish wrap/reset-on-enable semantics. With enable bits0, a zero counter is not evidence of no audio. Enabling counters would be a new diagnostic mutation, outside this read-only review.

Official frozen `rockchip_sai.c` hw_params lines537–639 computes lanes, programs CSR(lanes), then ch_per_lane=PCM_channels/lanes and SNB(ch_per_lane); frame width=fw_ratio*slot_width*ch_per_lane. The normal2-channel/1-lane/32-bit profile therefore requests2 slots and64 BCLK per frame. Header macros encode CSR(n)=(n−1)<<20 and SNB(n)=(n−1)<<11: field CSR=0 means one physical lane, while literal field1 would mean two. Distinguish logical lane count from register encoding.

The entire frozen driver references SLOT_MASK only in readable/writeable regmap classification. DATA_CNT appears only in readable/volatile classifications; counter enable macros are not used in the C file. No explicit mask or counter writes occur in hw_params/trigger. set_tdm_slot exists but does not supply a PIO-bank selector. Regmap's access policy is not an initialization write. The small reg_defaults table does not initialize slot masks.

Current formal PIO requests CSR(1), SNB(2), SBW32/VDW32, FW64/FPW32; source snapshot and hash included. Four physical FIFOs still being consumed in sequence is a verified root trace, but these definitions do not explain CPU data-port bank selection. All masks zero does not logically enable128 active serial slots: SNB determines configured slot count, with masks qualifying slots. Conversely, a hypothetical nonzero mask cannot automatically be blamed for the observed rotation without checking its affected configured slot and hardware semantics. No suggested mask trial writes are supplied.

Minimal next evidence: root may read offsets3c–60 and XFER while preserving the experiment, plus RXCR/TXCR/FSCR. If all masks0, missing mask enable is excluded under documented polarity. If active slot0/1 mask bits are1, record inherited state before choosing a separate correction. An unexplained DATA_CNT value cannot establish actual total slot count without its enable/unit semantics. No reset/20us repeat is proposed.

Primary evidence is previously frozen manufacturer RK3576 TRM V1.2, physical pages935–936 for masks/counters, plus XFER table in SAI-layout.txt. Original PDF provenance/hash in input.json is reused, not a new PDF extraction. This task hashes the actual read-only text and official SDK C/header, and snapshots current formal PIO. No SDK/device/formal/central-log writes; no tests claim silicon behavior.
