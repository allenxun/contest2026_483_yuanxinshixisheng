import copy
from pathlib import Path
import unittest
from audit_layout import parse,validate,overlap
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.model=parse(ROOT/'evidence/llama-native-link-20260910/llama-link.elf')
    def test_real_layout(self): self.assertTrue(validate(self.model)['layout_passed'])
    def test_cap_boundary(self):
        self.assertTrue(validate(self.model,0x40b40000)['layout_passed'])
        self.assertFalse(validate(self.model,0x40b3ffff)['layout_passed'])
    def test_old_cap(self): self.assertFalse(validate(self.model,0x40a00000)['layout_passed'])
    def test_half_open(self):
        self.assertFalse(overlap(1,2,2,3))
        self.assertTrue(overlap(1,3,2,4))
    def test_mutations(self):
        changes=[('entry',lambda m:m.update(entry=0x40400008)),
                 ('size',lambda m:m['loads'][2].update(filesz=0x400000)),
                 ('offset',lambda m:m['loads'][2].update(offset=m['file_bytes'])),
                 ('overlap',lambda m:m['loads'][1].update(physical=0x40400000,virtual=0x40400000)),
                 ('radio',lambda m:m['loads'][2].update(physical=0x50000000,virtual=0x50000000)),
                 ('heap',lambda m:m['loads'][2].update(memsz=0x8000000)),
                 ('stack',lambda m:m['symbols'].update(_e_initstack=0x40b41000)),
                 ('header',lambda m:m['image_header'].update(image_size=0x600000)),
                 ('rwx',lambda m:m['loads'][0].update(flags=7)),
                 ('misalign',lambda m:m['loads'][0].update(align=3))]
        for name,change in changes:
            with self.subTest(name=name):
                m=copy.deepcopy(self.model); change(m)
                self.assertFalse(validate(m)['layout_passed'])
if __name__=='__main__': unittest.main()
