"""Package locked firmware and decoder for one Fastboot RAM download.

This only creates files; it does not download, relocate, boot or flash.
Decoder must be copied to 0x80000000 BEFORE relocating firmware.
"""
import hashlib
import json
import zlib
from pathlib import Path

def prepare(firmware, model, output):
    fw=Path(firmware).read_bytes(); decoder=Path(model).read_bytes()
    assert hashlib.sha256(fw).hexdigest()=='c8f58b202842032ea155d877fb91003df70c2480039b93851a2e10c98c9da9ca'
    assert hashlib.sha256(decoder).hexdigest()=='0f58ca4bd77728d8e512b852eff58e9aeedd90cfa2016ae40379b4700a78da14'
    offset=0x1000000
    assert len(fw)<=offset
    payload=fw+bytes(offset-len(fw))+decoder
    assert len(payload)<=0x07000000
    output=Path(output); assert not output.exists()
    output.write_bytes(payload)
    report={'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),
            'crc32':'%08x'%(zlib.crc32(payload)&0xffffffff),
            'download_base':'0x40c00800','download_limit':'0x47c00800',
            'copy_order':['decoder','firmware'],'board_tested':False,'parts':[]}
    for name,data,off,target in [('decoder',decoder,offset,0x80000000),('firmware',fw,0,0x40400000)]:
        report['parts'].append({'name':name,'bytes':len(data),'offset':off,
            'source':hex(0x40c00800+off),'target':hex(target),
            'sha256':hashlib.sha256(data).hexdigest(),
            'crc32':'%08x'%(zlib.crc32(data)&0xffffffff)})
    output.with_suffix('.json').write_text(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    import sys
    print(json.dumps(prepare(*sys.argv[1:]),indent=2))
