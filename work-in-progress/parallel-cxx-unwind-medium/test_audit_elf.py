"""Synthetic ELF mutation tests; these are not a repaired firmware build."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('audit', str(HERE/'audit_elf.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def fixture(mutation=None):
    data = bytearray(4096)
    def put(offset,fmt,*values):
        struct.pack_into('<'+fmt,data,offset,*values)
    data[:6] = b'\x7fELF\x02\x01'
    put(18,'H',183)
    put(32,'QQ',64,2048)
    put(54,'HHHHH',56,1,64,6,1)
    put(64,'IIQQQQQQ',1,6 if mutation=='writable' else 4,0,0x400000,0x400000,2048,2048,4096)
    names = b'\0.shstrtab\0.eh_frame\0.gcc_except_table\0.symtab\0.strtab\0'
    data[256:256+len(names)] = names
    # One CIE, one backward-referencing FDE, one zero terminator.
    put(512,'IIIIII',4,0,4,12,1 if mutation=='terminator' else 0,0)
    if mutation=='cie':
        put(524,'I',88)
    symbols = [('_srodata',0x400000),('_erodata',0x400100 if mutation=='mmu' else 0x401000),
               ('_sinit',0x400280),('_einit',0x400288),
               ('k7_unwind_initialize',0x400300),('__register_frame',0x400320),
               ('__k7_eh_frame_start',0x400200),('__k7_eh_frame_end',0x400218)]
    put(640,'Q',0x400308 if mutation=='priority' else 0x400300)
    strings = b'\0'
    for i,(name,value) in enumerate(symbols):
        put(1024+24*i,'IBBHQQ',len(strings),0x12,0,0xfff1,value,0)
        strings += name.encode()+b'\0'
    data[1536:1536+len(strings)] = strings
    sections = [(0,0,0,0,0,0,0,0,0,0),
                (names.index(b'.shstrtab'),3,0,0,256,len(names),0,0,1,0),
                (names.index(b'.eh_frame'),1,2,0x400200,512,24,0,0,8,0),
                (names.index(b'.gcc_except_table'),1,2,0x400240,576,8,0,0,8,0),
                (names.index(b'.symtab'),2,0,0,1024,24*len(symbols),5,0,8,24),
                (names.index(b'.strtab'),3,0,0,1536,len(strings),0,0,1,0)]
    for i,section in enumerate(sections):
        put(2048+64*i,'IIQQQQIIQQ',*section)
    return data

class AuditTests(unittest.TestCase):
    def test_mutations(self):
        with tempfile.TemporaryDirectory(dir=str(HERE)) as directory:
            for mutation in [None,'writable','terminator','cie','mmu','priority']:
                with self.subTest(mutation=mutation):
                    path=Path(directory)/'fixture.elf'
                    path.write_bytes(fixture(mutation))
                    self.assertEqual(module.audit(path)['passed'], mutation is None)

if __name__=='__main__':
    unittest.main()
