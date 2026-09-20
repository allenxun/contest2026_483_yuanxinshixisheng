"""Pure local plan construction. Never accesses MMIO. Python 3.6+."""
SEL = 0x272003e4
GATE = 0x27200830
MUX = 0x2604408c
FIELDS = {SEL: 0x30, GATE: 0x4004, MUX: 0xff}


def word(mask, value):
    if not 0 < mask <= 0xffff or value & ~mask:
        raise ValueError('invalid HIWORD field')
    return (mask << 16) | value


def prepare(snapshot, evidence):
    required = ('exclusive_owner', 'shared_pclk_ready', 'reset_deasserted',
                'power_ready', 'pins_safe_to_reassign', 'xin24m_design_confirmed')
    if not all(evidence.get(k) is True for k in required):
        raise ValueError('not ready: missing external evidence')
    for a in FIELDS:
        if type(snapshot.get(a)) is not int or not 0 <= snapshot[a] <= 0xffffffff:
            raise ValueError('invalid snapshot')
    if not snapshot[GATE] & 0x4000:
        raise ValueError('functional clock already running: separate owner review')
    # Clock source may change only while the functional clock is gated.
    return [dict(address=SEL, mask=0x30, value=0x30, write=word(0x30, 0x30)),
            dict(address=GATE, mask=0x4, value=0, write=word(0x4, 0)),
            dict(barrier='verify controller EN=0 and IEN=0 under live PCLK; '
                         'STOP/idle and timing remain separate; abort if unknown'),
            dict(address=GATE, mask=0x4000, value=0, write=word(0x4000, 0)),
            dict(barrier='confirm inactive controller and safe released lines '
                         'before selecting pins; never issue START'),
            dict(address=MUX, mask=0xff, value=0xbb, write=word(0xff, 0xbb))]


def restore(snapshot, current, applied, quiescent):
    """applied: verified completed write operations only, in execution order.

    In-flight/uncertain writes must be resolved by readback before this call.
    Conflicts reject the whole restore plan; no blind rollback.
    """
    if quiescent is not True:
        raise ValueError('not quiescent: retain ownership')
    expected = dict(snapshot)
    owned = {}
    history = []
    for op in applied:
        a, m, v = op['address'], op['mask'], op['value']
        if a not in FIELDS or m & ~FIELDS[a] or op['write'] != word(m, v):
            raise ValueError('invalid applied operation')
        history.append((a, m, expected[a] & m))
        expected[a] = (expected[a] & ~m) | v
        owned[a] = owned.get(a, 0) | m
    if any((current[a] ^ expected[a]) & m for a, m in owned.items()):
        raise ValueError('owned field conflict: stop and retain ownership')
    return [dict(address=a, mask=m, value=v, write=word(m, v))
            for a, m, v in reversed(history)]
