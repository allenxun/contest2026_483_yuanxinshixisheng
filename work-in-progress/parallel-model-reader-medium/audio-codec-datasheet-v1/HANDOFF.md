# ES8388 documentation recovery

Found a manufacturer-branded **ES8388 User Guide, 2011-06-17, 28 pages**, hosted by [Radxa](https://dl.radxa.com/rock2/docs/hw/ds/ES8388%20user%20Guide.pdf). The local PDF is 1,706,304 bytes; SHA256 `6d25413e840d096186b21f9aa1eff8b58b95ea97d216a248c60ea178884d0457`. This is a third-party mirror, not a fresh download from Everest. No cryptographic manufacturer signature or applicability to the populated board revision was established.

Local filename search under E:/rk3576_data found no es8388/everest/codec/audio-PDF match. This does not exclude documents buried in archives or generically named files; no SDK/archive/image expansion was performed.

## Gap mapping

| Previous gap | Located evidence | Remaining work |
| --- | --- | --- |
| Complete recording sequence | User Guide §10.2 p26; original flow arrows visually reviewed in guide-26.png | Adapt the reference format/input choices; establish target settling and error/stop integration. |
| Differential LIN2/RIN2 | §7 pp12–14; §8.4 pp19–20 explicitly includes pair2 selection | Match actual microphone bias/circuit. Guide figure reuses an ES8328 label; do not substitute that figure for the K7 schematic. |
| Gain/ALC starting profile | §8.3 pp16–19 contains voice/music profiles | Validate clipping/noise with actual microphone; recommendations are not measured calibration. |
| Playback/standby | §10.3 p26, §10.5 p27, §10.6 p28 | No amplifier enable or hardware execution authorized by this recovery. DMA ownership and clock teardown remain target work. |
| Clock/slots | §5.2 p8 distinguishes16-bit/32-bit word clock ratios | Resolve slot profile with SAI; do not infer slots solely from sample storage width. |
| Register defaults/readback | Datasheet Rev5 §5.2 pp10–11 and §6 pp11–29 | Narrow masks can now be reviewed using documented fields; no blanket hardware-read whitelist or TARGET_REVIEWED promotion. |

The [Everest ES8388 datasheet Rev5.0, July2018, 36 pages](https://manuals.plus/m/bd624af22c64cb927c8e43b74e90e0cf87e67ead91628d6361e035bb06eda94d.pdf) was readable through the web PDF tool; an [ArmDesigner mirror](https://www.armdesigner.com/download/ES8388_datasheet.pdf) exposed the same text/version. Binary downloads failed, so **no local PDF hash is claimed for either**. It documents I2C register reading and address0x10 with CE low, register defaults, ADC controls, differential selectors, data mapping and format. Register addresses in chapter headings are decimal: register12 is0x0c, not0x12. It lists53 registers, consistent with0x00–0x34; the Linux0x35 write remains unexplained. The revision10 search result was not retrieved and is not a validated source.

## Conflicts requiring reconciliation

The guide's differential example writes0x0c=0x40 while its comment describes0x00 and separate left/right ADC data. Rev5 §6.2.4 distinguishes these data mappings. Treat this as a source conflict, not a reason to auto-copy the literal or comment. User Guide sample syntax also omits commas; it is reference pseudocode. Guide recording and standby flows now provide ordered operations, but not a demonstrated K7 capture-only sequence. Different analog component values and old document versions require review against actual hardware.

The documentation-only blocker is narrowed substantially; **hardware remains NOT_READY**. No kc_plan or review-bit changes were made. Use the recovered guide plus versioned datasheet to produce a separately reviewed plan after resolving discrepancies, actual part identity, bias/rails, initialization timing and A/C adapter contracts. No new field mock or transaction engine tests were repeated.

## Acquisition and inspection evidence

fetch-results.json preserves the initial three bounded attempts. Everest HTTPS failed TLS locally and timed out through web; pcbartists revision10 failed TLS locally/web502; LCSC returned non-PDF. A later ArmDesigner attempt failed certificate verification; manuals.plus returned403. No TLS verification was disabled, access controls bypassed, or certificate stores altered. Radxa succeeded with urllib timeout15s and5MiB response cap.

PDF text was extracted with pypdf. Poppler rendered physical pages19/26/27 to the included PNGs, which were visually inspected; missing-font warnings occurred for Symbol/ArialUnicode, so glyph-heavy values should be checked against the PDF before implementation. Flow direction and numeric labels on pages26/27 were legible. fitz was unavailable; no package installation was performed. guide-text.txt is a navigation aid, not an execution-order authority.

All files are confined to this candidate. No SDK, device, model, formal source or central log changes. Public source rights remain with their respective owners; no relicensing is implied.
