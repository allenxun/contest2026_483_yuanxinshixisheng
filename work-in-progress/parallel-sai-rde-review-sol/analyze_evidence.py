#!/usr/bin/env python3
"""Verify frozen review inputs and derive only mechanically checkable facts."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fifo_counts(raw):
    return [(raw >> shift) & 0x3F for shift in (0, 6, 12, 18)]


def load_hashes():
    rows = []
    for line in (HERE / "INPUTS.sha256").read_text(encoding="utf-8").splitlines():
        if line.strip():
            expected, relative = line.split(None, 1)
            rows.append((expected, relative.strip()))
    return rows


def main():
    mismatches = []
    for expected, relative in load_hashes():
        actual = sha256(ROOT / relative)
        if actual != expected:
            mismatches.append({"path": relative, "expected": expected, "actual": actual})

    pause = json.loads((ROOT / "work-in-progress/audio-pause-20260911/board-result.json").read_text(encoding="utf-8"))
    rxtrace = json.loads((ROOT / "evidence/audio-rxtrace-20260910/runtime-results.json").read_text(encoding="utf-8"))
    loopback = json.loads((ROOT / "evidence/audio-loopback-20260910/runtime-results.json").read_text(encoding="utf-8"))
    driver = (ROOT / "work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip/rockchip_sai.c").read_text(encoding="utf-8")
    header = (ROOT / "work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip/rockchip_sai.h").read_text(encoding="utf-8")
    s16_dir = ROOT / "work-in-progress/audio-s16-20260911"

    result = {
        "all_input_hashes_match": not mismatches,
        "mismatches": mismatches,
        "pause": {
            "pause_us": pause["pause_us"],
            "fifo_after_raw": pause["fifo_after"],
            "fifo_after_decoded": fifo_counts(int(pause["fifo_after"], 16)),
            "all_four_banks_nonempty": all(fifo_counts(int(pause["fifo_after"], 16))),
        },
        "rxtrace": {
            "trace_valid": rxtrace["trace_valid"],
            "first_eight_fifo_before": [f'{row["before"]:08x}' for row in rxtrace["rows"][:8]],
            "first_eight_words": [f'{row["word"]:08x}' for row in rxtrace["rows"][:8]],
        },
        "loopback": {
            "transport_completed": loopback["transport_completed"],
            "periodic_zero_samples_unresolved": loopback["periodic_zero_samples_unresolved"],
        },
        "linux_reference": {
            "sets_rdl_16": "SAI_DMACR_RDL(16)" in driver,
            "toggles_rde": "SAI_DMACR_RDE(en)" in driver,
            "capture_rxdr_width_4": "capture_dma_data.addr_width = DMA_SLAVE_BUSWIDTH_4_BYTES" in driver,
            "rdl_macro_is_n_minus_1": "#define SAI_DMACR_RDL(x)\t\t((x - 1) << 16)" in header,
        },
        "s16_artifact_boundary": {
            "board_result_present": (s16_dir / "board-result.json").exists(),
            "raw_runtime_logs": sorted(p.name for p in s16_dir.glob("*.log") if "build" not in p.name and "test" not in p.name),
        },
    }
    (HERE / "analysis-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
