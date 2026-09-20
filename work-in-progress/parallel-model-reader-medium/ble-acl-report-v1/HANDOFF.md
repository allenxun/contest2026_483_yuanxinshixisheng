# BLE ACL offline metadata report v1

Independent offline Python standard-library tool for the frozen ble-acl-diag-v1 format. No hardware, SDK, cloud calls or formal source modifications. All examples in this delivery are SYNTHETIC, not board evidence.

## Run

`C:/Users/pc2025/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B report.py before.txt after.txt`

Outputs JSON to stdout, including SHA256 of the exact two input byte strings, parsed raw values, uint32 modulo deltas, decreasing-counter names, before/after last errors, flow completion evidence and interpretation limits. It does not copy logs or print payloads. Redirect stdout only into an authorized output directory. Invalid input exits 2 with no report JSON.

Each file must contain exactly one consecutive six-line `RADIO BTM` block emitted by diag-v1, all 25 fields in the fixed order, each line newline-terminated. LF/CRLF accepted. Unrelated preamble/trailer is ignored, but BTM-looking fragments, duplicate/reordered/unknown fields or lines, missing fields, integer overflow, extra blocks, interleaving and unterminated BTM lines are rejected. This strict choice may require extracting an intact block from noisy console output; do not reconstruct missing values. Legacy BLE connected/status lines are neither interpreted nor treated as protocol proof.

## Interpretation limits

Use chronological observations from the same running application/counter lifetime. There is no epoch or timestamp in this format: the tool cannot verify chronology, reset vs wrap, or that an intact-looking block did not combine different acquisitions. `counter_decreases` exposes that ambiguity; modulo deltas are conditional rather than proof of actual event count, and multiple full wraps are unknowable. No inferred stage-loss arithmetic.

Every field is atomic individually, but the block is not a coherent snapshot. ACK may precede a send-return counter and last errors/status can race their counts. Last errors persist after successful events. FLOW_COMPLETE=0 reports status=null even when the stored byte is zero, never success. With a positive count, status is only the last observed command-completion byte, potentially predating the interval; the pair still is not coherent. Queue/send/link ACK/GAP do not establish HCI command success, pairing, GATT, remote application receipt or usable BLE.

## Tests and fixed inputs

`python -B run_tests.py` runs 16 unit tests and a CLI truncated-input rejection check, subprocess timeouts 15 seconds. Raw output is test-output.txt. Tests cover complete/hash, missing/duplicate/truncated block, duplicate field, ranges, wrap, zero/failed flow completion, interleaving, CRLF, persistent errors and noncoherent stage counts. Synthetic-before/after/report are reproducible examples and must not be presented as device evidence.

inputs.json hashes the frozen upstream candidate header and main source which define the six lines, plus the exact synthetic before/after inputs. The analyzer also hashes each runtime input independently. No dependency installation needed; target firmware unchanged.
