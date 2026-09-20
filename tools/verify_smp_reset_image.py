"""Verify the exact wifi-ip build and ELF load bounds before RAM boot."""
import hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def verify(build):
    build=Path(build).resolve();assert build==ROOT/'artifacts/smp-reset-20260910'
    report=json.loads((ROOT/'evidence/build/smp-reset-20260910/verification.json').read_text())
    assert report['build_exit_code']==0
    for name,digest in report['sources'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
    for name,item in report['artifacts'].items():
        data=(build/name).read_bytes();assert len(data)==item['bytes']
        assert hashlib.sha256(data).hexdigest()==item['sha256']
    cfg=(build/'.config').read_text().splitlines()
    assert 'CONFIG_BOARDCTL_RESET=y' in cfg
    assert 'CONFIG_SMP_NCPUS=2' in cfg
    assert '# CONFIG_NSH_DISABLE_REBOOT is not set' in cfg
    binary=(build/'nuttx.bin').read_bytes();elf=(build/'nuttx').read_bytes()
    assert elf[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',elf,18)[0]==183
    entry,phoff=struct.unpack_from('<QQ',elf,24);step,count=struct.unpack_from('<HH',elf,54)
    assert entry==0x40400000 and step==56 and count==3
    ends=[]
    for i in range(count):
        kind,flags,offset,virtual,physical,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',elf,phoff+i*step)
        assert kind==1 and flags in (4,5,6) and virtual==physical
        # Explicit 6 MiB image reservation, well below DTB/firmware staging.
        assert entry<=physical<=physical+memsz<=0x40a00000
        assert filesz<=memsz and offset+filesz<=len(elf)
        relative=physical-entry;assert relative+filesz<=len(binary)
        assert binary[relative:relative+filesz]==elf[offset:offset+filesz]
        ends.append(physical+memsz)
    return dict(entry=hex(entry),memory_bytes=max(ends)-entry,sha256=hashlib.sha256(binary).hexdigest())
if __name__=='__main__':print(verify(ROOT/'artifacts/smp-reset-20260910'))
