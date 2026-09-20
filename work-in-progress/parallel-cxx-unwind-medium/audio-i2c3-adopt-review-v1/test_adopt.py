import unittest
from adopt import adopt,restore,SEL,GATE,MUX

class Tests(unittest.TestCase):
    def setUp(self):
        self.s={SEL:0,GATE:0,MUX:0}
        self.e=dict.fromkeys(('exclusive_owner','mapping_confirmed',
            'shared_pclk_ready','parent_gate_ready','power_ready',
            'pins_safe_to_reassign','xin24m_design_confirmed',
            'controller_access_quiescent','external_lines_released'),True)
    def test_plan_and_all_prefix_restore(self):
        p=[x for x in adopt(self.s,self.e,0,0,0) if 'address' in x]
        self.assertEqual([x['write'] for x in p],
            [0x40004000,0x00300030,0x40000000,0x00ff00bb])
        for n in range(5):
            c=dict(self.s)
            for x in p[:n]:
                a,m,v=x['address'],x['mask'],x['value'];c[a]=(c[a]&~m)|v
            for x in restore(self.s,c,p[:n],True):
                a,m,v=x['address'],x['mask'],x['value'];c[a]=(c[a]&~m)|v
            self.assertEqual(c,self.s)
    def test_reject(self):
        for con,ien,rst in ((1,0,0),(8,0,0),(16,0,0),(0,1,0),
                            (0,0,4),(0,0,0x4000)):
            with self.assertRaises(ValueError):adopt(self.s,self.e,con,ien,rst)
        for k in self.e:
            e=dict(self.e);e[k]=False
            with self.assertRaises(ValueError):adopt(self.s,e,0,0,0)
    def test_conflict(self):
        p=[x for x in adopt(self.s,self.e,0,0,0) if 'address' in x]
        with self.assertRaises(ValueError):restore(self.s,self.s,p,True)

if __name__=='__main__':unittest.main(verbosity=2)
