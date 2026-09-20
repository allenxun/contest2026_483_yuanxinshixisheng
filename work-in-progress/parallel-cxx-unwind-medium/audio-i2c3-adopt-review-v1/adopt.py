"""Pure plan only. No MMIO; caller must substantiate every evidence field."""
from frozen_plan import SEL, GATE, MUX, word, restore


def adopt(s, e, con, ien, reset):
    needed = ('exclusive_owner', 'mapping_confirmed', 'shared_pclk_ready',
              'parent_gate_ready', 'power_ready', 'pins_safe_to_reassign',
              'xin24m_design_confirmed', 'controller_access_quiescent',
              'external_lines_released')
    if not all(e.get(k) is True for k in needed):
        raise ValueError('missing evidence')
    for v in list(s.values()) + [con, ien, reset]:
        if type(v) is not int or not 0 <= v <= 0xffffffff:
            raise ValueError('bad snapshot')
    if s[GATE] & 0x4004 or reset & 0x4004:
        raise ValueError('gated or reset; do not read/adopt controller')
    if con & 0x19 or ien != 0:
        raise ValueError('EN/START/STOP/IEN nonzero: do not take over')
    def op(a,m,v):
        return dict(address=a,mask=m,value=v,write=word(m,v))
    # Gate only our verified idle functional clock while changing parent.
    return [op(GATE,0x4000,0x4000),op(SEL,0x30,0x30),
            op(GATE,0x4000,0),
            dict(barrier='recheck inactive controller and released lines; '
                         'no START and no timing defaults'),
            op(MUX,0xff,0xbb)]
