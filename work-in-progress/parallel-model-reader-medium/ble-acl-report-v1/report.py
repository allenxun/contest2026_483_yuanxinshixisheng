"""Offline parser for frozen ble-acl-diag-v1 six-line BTM format."""
import argparse
import hashlib
import json
import re
from pathlib import Path

GROUPS = (
 ('ACL_QUEUED','ACL_SEND_OK','ACL_SEND_FAIL','ACL_ACK_MATCH'),
 ('ACL_ACK_OTHER','ACL_ACK_WAIT_FAIL','PORT5_SLOT','SLOT_DECODE_FAIL'),
 ('PORT5_SLOT_DECODE_FAIL','HCI_DECODE_FAIL','PORT5_HCI_DECODE_FAIL','READY_REJECT'),
 ('RX_LOCK_FAIL','H4_ACL','H4_EVENT','H4_SCO'),
 ('H4_VENDOR','H4_OTHER','LINK_ACK','FLOW_COMPLETE'),
 ('last_send','last_decode','last_ready','last_wait','flow_status'),
)
COUNTERS = sum(GROUPS[:5], ())
ERRORS = GROUPS[5][:4]
PREFIX = 'RADIO BTM '


def parse(raw):
    text = raw.decode('utf-8', errors='strict')
    lines = text.splitlines(keepends=True)
    found = []
    positions = []
    for index, line in enumerate(lines):
        # Any BTM-looking fragment must parse; ordinary preamble/status is ignored.
        if 'RADIO BTM' in line:
            if not line.endswith('\n'):
                raise ValueError('unterminated BTM line')
            positions.append(index)
            if not line.startswith(PREFIX):
                raise ValueError('prefixed or truncated BTM line')
            found.append(line[len(PREFIX):])
    if len(found) != 6:
        raise ValueError('expected exactly six BTM lines (one status block)')
    if positions != list(range(positions[0], positions[0]+6)):
        raise ValueError('interleaved BTM block')
    values = {}
    for body, keys in zip(found, GROUPS):
        tokens = body.split()
        if len(tokens) != len(keys):
            raise ValueError('missing or extra field')
        for token, key in zip(tokens, keys):
            match = re.fullmatch(r'([A-Za-z0-9_]+)=(-?[0-9]+)', token)
            if not match or match[1] != key or key in values:
                raise ValueError('unknown, duplicate, reordered or malformed field')
            value = int(match[2])
            low, high = (-(1 << 31), (1 << 31)-1) if key in ERRORS else (0, (1 << 32)-1)
            if not low <= value <= high:
                raise ValueError('field out of range: ' + key)
            values[key] = value
    if values['flow_status'] > 255:
        raise ValueError('flow status must be a controller status byte')
    return values


def analyze(before_raw, after_raw):
    before, after = parse(before_raw), parse(after_raw)
    delta = {k: (after[k]-before[k]) & 0xffffffff for k in COUNTERS}
    notes = []
    if delta['ACL_QUEUED']:
        notes.append('Software ACL queue insertions observed; this does not prove transport submission.')
    if delta['ACL_SEND_FAIL']:
        notes.append('Transport send returned failure during the interval; inspect last_send and worker status.')
    if delta['ACL_ACK_WAIT_FAIL'] or delta['ACL_ACK_OTHER']:
        notes.append('ACK timeout/error or unmatched ACK observed; existing matching ignores sequence identity.')
    if delta['PORT5_SLOT_DECODE_FAIL'] or delta['PORT5_HCI_DECODE_FAIL']:
        notes.append('Port-5 claimed traffic reached a decoder and was rejected; inspect last_decode.')
    if delta['READY_REJECT'] or delta['RX_LOCK_FAIL']:
        notes.append('Bridge readiness or RX lock rejection observed after decode; inspect last_ready.')
    if delta['PORT5_SLOT'] == 0:
        notes.append('No port-5 count increase in these snapshots; this alone does not prove controller silence.')
    if delta['ACL_ACK_MATCH']:
        notes.append('Existing channel/pending ACK predicate matched; this is not HCI, GATT or remote application success.')
    if not notes:
        notes.append('No selected fault category increased; no protocol success can be inferred.')
    def flow(v):
        return {'count': v['FLOW_COMPLETE'], 'status': v['flow_status'] if v['FLOW_COMPLETE'] else None,
                'meaning': 'last observed Command Complete status, possibly predating interval' if v['FLOW_COMPLETE'] else 'no completion evidence; stored zero is not success'}
    return {
        'input_sha256': {'before': hashlib.sha256(before_raw).hexdigest(), 'after': hashlib.sha256(after_raw).hexdigest()},
        'before': before, 'after': after, 'uint32_modulo_delta': delta,
        'counter_decreases': [k for k in COUNTERS if after[k] < before[k]],
        'last_error_before_after': {k: {'before': before[k], 'after': after[k]} for k in ERRORS},
        'flow_complete': {'before': flow(before), 'after': flow(after)},
        'evidence': notes,
        'limitations': [
            'Requires same process/counter lifetime and chronological inputs; these metadata cannot verify either. Restart/reset and wrap cannot be distinguished.',
            'Modulo differences are not absolute event counts if one or more full 2^32 wraps occurred.',
            'Each status field is atomic but six lines are not a coherent snapshot. Do not subtract stages to infer lost packets or impose queued >= send >= ACK.',
            'Last errors persist across successful operations and may race counts; changed errors cannot be assigned to a specific packet.',
            'FLOW_COMPLETE count/status are separately read; a positive count does not make status a coherent pair or prove current flow configuration.',
            'Queued, send return, link ACK, H4 category and GAP connection do not prove GATT, pairing, remote receipt or application success.'
        ]
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('before', type=Path)
    ap.add_argument('after', type=Path)
    args = ap.parse_args()
    try:
        result = analyze(args.before.read_bytes(), args.after.read_bytes())
    except (OSError, ValueError) as e:
        ap.exit(2, 'invalid input: ' + str(e) + '\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
