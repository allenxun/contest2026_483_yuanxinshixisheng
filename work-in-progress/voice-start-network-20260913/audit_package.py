import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
BUILD = Path('/home/swl/openvela/cmake_out/velavision_voice_start_network_20260913')
sys.path.insert(0, str(PROJECT / 'tools'))
from audit_arm64_unwind import audit

report = json.loads((HERE / 'result.json').read_text())
assert report['build_exit_code'] == 0
unwind = audit(BUILD / 'nuttx')
(HERE / 'unwind.json').write_text(json.dumps(unwind, indent=2))
assert unwind['passed']
elf = (BUILD / 'nuttx').read_bytes()
raw = (BUILD / 'nuttx.bin').read_bytes()
assert hashlib.sha256(raw).hexdigest() == report['artifacts']['nuttx.bin']['sha256']
assert elf[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', elf, 18)[0] == 183
entry, phoff = struct.unpack_from('<QQ', elf, 24)
step, count = struct.unpack_from('<HH', elf, 54)
assert entry == 0x40400000 and step == 56
loads = []
for i in range(count):
    kind, flags, offset, virtual, physical, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', elf, phoff + i * step)
    if kind != 1:
        continue
    assert virtual == physical and entry <= physical <= physical + memsz < 0x46000000
    assert filesz <= memsz and offset + filesz <= len(elf)
    relative = physical - entry
    assert raw[relative:relative + filesz] == elf[offset:offset + filesz]
    loads.append({'address': hex(physical), 'memory_bytes': memsz})
assert loads and 0 < len(raw) < 0x01000000
# Explicit intermediate RAM staging avoids overlapping source/destination.
output = HERE / 'voice-start-network.bin'
with output.open('xb') as f:
    f.write(raw)
record = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
          'crc32': '%08x' % (zlib.crc32(raw) & 0xffffffff),
          'download_address': '0x40c00800', 'stage_address': '0x46000000',
          'boot_address': '0x40400000', 'flash_commands': False,
          'elf_loads': loads, 'unwind_passed': True}
(HERE / 'package.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
