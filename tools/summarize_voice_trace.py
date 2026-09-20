"""Report observed trace boundaries, never infer a root cause from a timeout."""
import argparse
import json
import re
from pathlib import Path


def summarize(raw):
    text = raw.decode('utf-8', errors='replace').replace('\r', '')
    events = re.findall(r'^ORT_ADD (BEGIN|END) ([a-zA-Z0-9_-]+)\s*$', text, re.M)
    pending = None
    last_returned = None
    for kind, stage in events:
        if kind == 'BEGIN':
            pending = stage
        elif pending == stage:
            last_returned = stage
            pending = None
    passed = 'ORT_ADD PASS values=11,22,33,44' in text
    # PASS is printed only after the final cleanup call returns.
    if passed and pending == 'cleanup':
        last_returned = 'cleanup'
        pending = None
    return dict(trace_seen=bool(events),
                passed=passed,
                last_returned_stage=last_returned,
                last_unreturned_stage=pending,
                failure_messages=re.findall(r'^ORT_ADD FAIL[^\n]*', text, re.M),
                observation=('No instrumented entry observed; application entry is unconfirmed'
                             if not events else 'Trace boundaries only; root cause undetermined'),
                asr_tested=False, tts_tested=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('raw', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.raw.read_bytes())
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
