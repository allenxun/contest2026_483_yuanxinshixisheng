import hashlib,json,zlib
from pathlib import Path
root=Path(__file__).resolve().parent
old=Path('/home/swl/openvela/work/native-asr-model-session/encoder1/encoder-first-firmware.bin').read_bytes()
assert hashlib.sha256(old).hexdigest()=='9951c2742be81d6fad8ed3a432c2d294271748f2cfcbb9241235bc8369f5071b'
fw=Path('/home/swl/openvela/cmake_out/velavision_voice_asr_microphone_20260911/nuttx.bin').read_bytes()
assert hashlib.sha256(fw).hexdigest()=='2ac0ebef89c5bb21dfe57a29a1efa3a6b199e3fea4c8e13c1d8769f603ec61fa'
data=old[:0x6000000]+fw
assert len(data)<=0x07000000
p=root/'first-firmware.bin'
assert not p.exists()
p.write_bytes(data)
m={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'crc32':'%08x'%(zlib.crc32(data)&0xffffffff),'firmware_bytes':len(fw),'firmware_crc32':'%08x'%(zlib.crc32(fw)&0xffffffff)}
(root/'transfer.json').write_text(json.dumps(m,indent=2));print(json.dumps(m))
