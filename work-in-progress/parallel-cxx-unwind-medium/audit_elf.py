"""Dependency-free ELF64 LE ARM64 static unwind gate (Python >=3.6).

This validates placement, CIE/FDE record framing and first initializer, not
DWARF instructions, FDE PC coverage, startup execution or exception behavior.
Exit 0: static gates pass; exit 1: reject; exit 2: malformed/unsupported ELF.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

def audit(path):
    data = Path(path).read_bytes()
    def unpack(fmt, offset):
        return struct.unpack_from('<' + fmt, data, offset)
    assert data[:6] == b'\x7fELF\x02\x01', 'requires ELF64 little endian'
    assert unpack('H', 18)[0] == 183, 'requires ARM64'
    phoff, shoff = unpack('QQ', 32)
    phentsize, phnum, shentsize, shnum, shstrndx = unpack('HHHHH', 54)
    sections = [unpack('IIQQQQIIQQ', shoff+i*shentsize) for i in range(shnum)]
    def blob(section):
        return data[section[4]:section[4]+section[5]]
    names = blob(sections[shstrndx])
    def string(table, offset):
        return table[offset:].split(b'\0', 1)[0].decode('utf-8', 'replace')
    named = {string(names,s[0]):s for s in sections}
    symbols = {}
    for s in sections:
        if s[1] == 2:
            strings = blob(sections[s[6]])
            for off in range(s[4], s[4]+s[5], s[9]):
                n, info, other, index, value, size = unpack('IBBHQQ', off)
                if index:
                    symbols[string(strings,n)] = (value,size)
    loads = [unpack('IIQQQQQQ', phoff+i*phentsize) for i in range(phnum)]
    loads = [p for p in loads if p[0] == 1]
    def readva(addr,size):
        for p in loads:
            if p[3] <= addr and addr+size <= p[3]+p[5]:
                return data[p[2]+addr-p[3]:p[2]+addr-p[3]+size]
        raise ValueError('address is not file-backed PT_LOAD')
    checks = {}
    def check(name,value):
        checks[name] = bool(value)
    eh = named.get('.eh_frame')
    lsda = named.get('.gcc_except_table')
    check('eh_frame_present', eh and eh[5] > 4)
    check('lsda_consolidated_nonempty', lsda and lsda[5] > 0)
    check('no_orphan_lsda', not any(n.startswith('.gcc_except_table.') for n in named))
    counts = {'cie':0,'fde':0}
    if eh:
        raw = blob(eh)
        pos = 0
        terminated = False
        framing_ok = True
        cies = set()
        while pos+4 <= len(raw):
            length = struct.unpack_from('<I', raw, pos)[0]
            if length == 0:
                terminated = True
                framing_ok &= not any(raw[pos:])
                break
            if length == 0xffffffff or length < 4 or pos+4+length > len(raw):
                framing_ok = False
                break
            cie = struct.unpack_from('<I', raw, pos+4)[0]
            if cie == 0:
                cies.add(pos)
                counts['cie'] += 1
            else:
                counts['fde'] += 1
                framing_ok &= pos+4-cie in cies
            pos += length+4
        check('valid_records_terminal_zero_no_hidden_records', framing_ok and terminated and counts['fde'] > 0)
    for name,sec in [('.eh_frame',eh),('.gcc_except_table',lsda)]:
        if sec:
            check(name+'_readonly_file_load', any(p[1]==4 and p[3]<=sec[3] and sec[3]+sec[5]<=p[3]+p[5] for p in loads))
            check(name+'_inside_rodata_mmu_range', symbols.get('_srodata',(2**64,))[0] <= sec[3] and sec[3]+sec[5] <= symbols.get('_erodata',(0,))[0])
    check('registration_symbol', '__register_frame' in symbols)
    init = symbols.get('_sinit', (0,))[0]
    end = symbols.get('_einit', (0,))[0]
    hook = symbols.get('k7_unwind_initialize', (0,))[0]
    first = struct.unpack('<Q', readva(init,8))[0] if end-init >= 8 else 0
    check('first_initializer_is_unwind_registration', hook != 0 and first == hook)
    if eh:
        check('start_symbol_exact', symbols.get('__k7_eh_frame_start',(0,))[0] == eh[3])
        check('end_symbol_exact', symbols.get('__k7_eh_frame_end',(0,))[0] == eh[3]+eh[5])
    return {'elf':str(Path(path).resolve()), 'sha256':hashlib.sha256(data).hexdigest(),
            'checks':checks, 'records':counts, 'first_initializer':hex(first),
            'passed':all(checks.values()), 'hardware_tested':False,
            'limitations':['No startup call-order proof', 'No full DWARF/FDE PC coverage proof',
                           'No registration call disassembly proof', 'No runtime exception proof']}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('elf')
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        result = audit(args.elf)
    except (AssertionError, ValueError, IndexError, KeyError, struct.error) as error:
        result = {'passed':False, 'malformed':str(error)}
    rendered = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(rendered+'\n', encoding='utf-8')
    print(rendered)
    raise SystemExit(0 if result['passed'] else 2 if 'malformed' in result else 1)
