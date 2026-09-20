import unittest
from plan import SEL, GATE, MUX, prepare, restore, word


class Tests(unittest.TestCase):
    def setUp(self):
        self.s = {SEL: 0xa505, GATE: 0xc005, MUX: 0x1234}
        self.e = dict.fromkeys(('exclusive_owner', 'shared_pclk_ready',
            'reset_deasserted', 'power_ready', 'pins_safe_to_reassign',
            'xin24m_design_confirmed'), True)

    def test_words(self):
        p = [x for x in prepare(self.s, self.e) if 'address' in x]
        self.assertEqual([x['write'] for x in p],
                         [0x00300030, 0x00040000, 0x40000000, 0x00ff00bb])

    def test_every_prefix_restore_and_unrelated_change(self):
        p = [x for x in prepare(self.s, self.e) if 'address' in x]
        for n in range(5):
            c = dict(self.s)
            for x in p[:n]:
                a,m,v=x['address'],x['mask'],x['value']
                c[a]=(c[a]&~m)|v
            c[SEL] ^= 1
            for x in restore(self.s,c,p[:n],True):
                a,m,v=x['address'],x['mask'],x['value']
                c[a]=(c[a]&~m)|v
            self.assertEqual(c,{SEL:self.s[SEL]^1,GATE:self.s[GATE],MUX:self.s[MUX]})

    def test_conflicts(self):
        p = [x for x in prepare(self.s,self.e) if 'address' in x]
        c=dict(self.s)
        for x in p:
            a,m,v=x['address'],x['mask'],x['value']
            c[a]=(c[a]&~m)|v
        for a,bit in ((SEL,0x10),(GATE,4),(GATE,0x4000),(MUX,1)):
            bad=dict(c);bad[a]^=bit
            with self.assertRaises(ValueError):
                restore(self.s,bad,p,True)
        with self.assertRaises(ValueError): restore(self.s,self.s,[],False)

    def test_gates(self):
        for k in self.e:
            e=dict(self.e);e[k]=False
            with self.assertRaises(ValueError): prepare(self.s,e)
        s=dict(self.s);s[GATE]&=~0x4000
        with self.assertRaises(ValueError): prepare(s,self.e)
        with self.assertRaises(ValueError): word(0x30,0x40)


if __name__ == '__main__': unittest.main(verbosity=2)
