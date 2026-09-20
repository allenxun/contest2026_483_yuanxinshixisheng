"""Two bounded RAM transfers, fixed encoder hash; no device access."""
import hashlib,json,zlib
from pathlib import Path

def package(model,firmware,expected_firmware,out):
    out=Path(out);enc=Path(model).read_bytes();fw=Path(firmware).read_bytes()
    assert len(enc)==166189616
    assert hashlib.sha256(enc).hexdigest()=='f81f9e656e21bc6c8350b7a04e3563bee3552dd0e047a44b5e9c978fd188c1af'
    assert hashlib.sha256(fw).hexdigest()==expected_firmware
    split=0x6000000;offset=0x1000000
    assert len(fw)<=offset
    first=enc[:split];second=fw+bytes(offset-len(fw))+enc[split:]
    assert first+second[offset:]==enc
    assert all(0<len(x)<=0x07000000 for x in (first,second))
    assert 0x80000000+len(enc)<0xa0000000
    out.mkdir(exist_ok=True)
    records=[]
    for name,data in [('encoder-part1.bin',first),('encoder-part2-firmware.bin',second)]:
        p=out/name
        assert not p.exists(),'Refuse to overwrite transfer artifacts'
        p.write_bytes(data)
        records.append(dict(file=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),crc32='%08x'%(zlib.crc32(data)&0xffffffff)))
    result=dict(transfers=records,encoder_bytes=len(enc),encoder_crc32='%08x'%(zlib.crc32(enc)&0xffffffff),
        split=split,second_encoder_offset=offset,first_target='0x80000000',second_target=hex(0x80000000+split),
        firmware_bytes=len(fw),firmware_sha256=expected_firmware,firmware_crc32='%08x'%(zlib.crc32(fw)&0xffffffff),
        board_tested=False,required_order=['part1 copy + CRC','part2 encoder copy + full encoder CRC','firmware copy + CRC','boot'])
    (out/'transfer-manifest.json').write_text(json.dumps(result,indent=2));return result

if __name__=='__main__':
    import sys
    print(json.dumps(package(*sys.argv[1:]),indent=2))
