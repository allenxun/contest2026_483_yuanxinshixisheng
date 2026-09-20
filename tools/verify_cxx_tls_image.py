"""Verify immutable C++ candidate artifacts and loadable ELF bounds."""
import hashlib
import json
import struct
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
REV = 'cxx-tls-20260910'

def verify(build):
    build = Path(build).resolve()
    assert build == ROOT/'artifacts'/REV
    report = json.loads((ROOT/'evidence/build'/REV/'verification.json').read_text())
    assert report['build_exit_code'] == 0
    for rel, digest in report['sources'].items():
        assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest() == digest, rel
    for name, item in report['artifacts'].items():
        data = (build/name).read_bytes()
        assert len(data) == item['bytes']
        assert hashlib.sha256(data).hexdigest() == item['sha256']
    cfg = (build/'.config').read_text().splitlines()
    for line in ['CONFIG_EXAMPLES_K7CXX=y','CONFIG_LIBCXX=y','CONFIG_LIBCXXABI=y',
                 'CONFIG_CXX_EXCEPTION=y','CONFIG_CXX_RTTI=y','CONFIG_TLS_NELEM=8',
                 'CONFIG_TLS_TASK_NELEM=8','CONFIG_SMP_DEFAULT_CPUSET=0x1',
                 'CONFIG_NCPUS=8','CONFIG_SMP_NCPUS=8','CONFIG_BOARDCTL_RESET=y']:
        assert line in cfg, line
    binary = (build/'nuttx.bin').read_bytes()
    elf = (build/'nuttx').read_bytes()
    assert elf[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H',elf,18)[0] == 183
    entry, phoff = struct.unpack_from('<QQ',elf,24)
    step, count = struct.unpack_from('<HH',elf,54)
    assert entry == 0x40400000 and step == 56 and count == 3
    ends = []
    for i in range(count):
        kind, flags, offset, virtual, physical, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ',elf,phoff+i*step)
        assert kind == 1 and flags in (4,5,6) and virtual == physical
        assert entry <= physical <= physical+memsz <= 0x40a00000
        assert filesz <= memsz and offset+filesz <= len(elf)
        relative = physical-entry
        assert relative+filesz <= len(binary)
        assert binary[relative:relative+filesz] == elf[offset:offset+filesz]
        ends.append(physical+memsz)
    return dict(entry=hex(entry),memory_bytes=max(ends)-entry,
                sha256=hashlib.sha256(binary).hexdigest())

if __name__ == '__main__':
    print(json.dumps(verify(ROOT/'artifacts'/REV)))
