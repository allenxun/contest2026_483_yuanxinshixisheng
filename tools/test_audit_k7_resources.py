import unittest
from audit_k7_resources import span,ranges,subtract,parse
class ResourceTests(unittest.TestCase):
 def test_high_address(self):
  raw=(0x100000000).to_bytes(8,'big')+(0x40000000).to_bytes(8,'big')
  self.assertEqual(ranges(raw,2,2),[span(0x100000000,0x40000000)])
 def test_reserved_hole(self):
  self.assertEqual(subtract([span(100,100)],[span(120,20)]),[span(100,20),span(140,60)])
 def test_overlapping_exclusions(self):
  self.assertEqual(subtract([span(100,100)],[span(90,40),span(120,50)]),[span(170,30)])
 def test_full_exclusion(self):self.assertEqual(subtract([span(100,20)],[span(0,1000)]),[])
 def test_adjacent_exclusion(self):self.assertEqual(subtract([span(100,20)],[span(120,10)]),[span(100,20)])
 def test_bad_reg(self):
  with self.assertRaises(ValueError):ranges(b'123',2,2)
 def test_overflow(self):
  with self.assertRaises(ValueError):span((1<<64)-1,2)
 def test_short_fdt(self):
  with self.assertRaises(ValueError):parse(bytes(39))
if __name__=='__main__':unittest.main()
