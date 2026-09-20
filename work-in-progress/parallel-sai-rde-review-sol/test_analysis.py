#!/usr/bin/env python3
"""Pure-host checks for the FIFO-level decoder and frozen evidence invariants."""

import json
import subprocess
import sys
from pathlib import Path

from analyze_evidence import HERE, fifo_counts


assert fifo_counts(0x00082082) == [2, 2, 2, 2]
assert fifo_counts(0x00000002) == [2, 0, 0, 0]
assert fifo_counts(0x00000080) == [0, 2, 0, 0]
assert fifo_counts(0x00002000) == [0, 0, 2, 0]
assert fifo_counts(0x00080000) == [0, 0, 0, 2]

run = subprocess.run([sys.executable, str(HERE / "analyze_evidence.py")], check=False)
assert run.returncode == 0
result = json.loads((HERE / "analysis-result.json").read_text(encoding="utf-8"))
assert result["all_input_hashes_match"]
assert result["pause"]["fifo_after_decoded"] == [2, 2, 2, 2]
assert result["pause"]["all_four_banks_nonempty"]
assert result["rxtrace"]["first_eight_fifo_before"] == [
    "00000002", "00000001", "00000080", "00000040",
    "00002000", "00001000", "00080000", "00040000",
]
assert result["rxtrace"]["first_eight_words"] == [
    "ffffffff", "ffffffff", "00000000", "00000000",
    "00000000", "00000000", "00000000", "00000000",
]
assert result["linux_reference"] == {
    "sets_rdl_16": True,
    "toggles_rde": True,
    "capture_rxdr_width_4": True,
    "rdl_macro_is_n_minus_1": True,
}
print("PASS: hashes, FIFO decode, RX trace sequence, loopback and Linux reference invariants")
