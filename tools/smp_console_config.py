"""Read the console rate from the immutable, hash-checked firmware config."""
import hashlib
import json
import re
from pathlib import Path


def console_baud(root: Path, revision: str) -> int:
    report = json.loads((root / 'evidence/build' / revision / 'verification.json').read_text())
    raw = (root / 'artifacts' / revision / '.config').read_bytes()
    expected = report['artifacts']['.config']
    if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
        raise ValueError('Firmware config does not match immutable build report')
    values = re.findall(rb'^CONFIG_16550_UART0_BAUD=(\d+)\r?$', raw, re.M)
    if len(values) != 1:
        raise ValueError('Expected exactly one UART0 console baud')
    return int(values[0])
