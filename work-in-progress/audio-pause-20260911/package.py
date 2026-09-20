import hashlib,json,zlib
from pathlib import Path
r=Path(__file__).resolve().parent
report=json.loads((r/'build-result.json').read_text());assert report['exit_code']==0
fw=Path('/home/swl/openvela/cmake_out/velavision_audio_pause_20260911/nuttx.bin').read_bytes()
assert hashlib.sha256(fw).hexdigest()==report['sha256']
old=Path('/home/swl/openvela/work/native-asr-model-session/encoder1/encoder-first-firmware.bin').read_bytes()
assert hashlib.sha256(old).hexdigest()=='9951c2742be81d6fad8ed3a432c2d294271748f2cfcbb9241235bc8369f5071b'
data=old[:0x6000000]+fw;assert len(data)<=0x7000000
with (r/'first-firmware.bin').open('xb') as f:f.write(data)
meta=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),crc32='%08x'%(zlib.crc32(data)&0xffffffff),firmware_bytes=len(fw),firmware_crc32='%08x'%(zlib.crc32(fw)&0xffffffff))
(r/'transfer.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta))
