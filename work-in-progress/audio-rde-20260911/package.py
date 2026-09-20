import hashlib
import json
import zlib
from pathlib import Path

root = Path(__file__).resolve().parent
report = json.loads((root / 'build-attempt2-result.json').read_text())
assert report['exit_code'] == 0
firmware = Path('/home/swl/openvela/cmake_out/velavision_audio_s16_20260911/nuttx.bin').read_bytes()
assert hashlib.sha256(firmware).hexdigest() == report['sha256']
old = Path('/home/swl/openvela/work/native-asr-model-session/encoder1/encoder-first-firmware.bin').read_bytes()
assert hashlib.sha256(old).hexdigest() == '9951c2742be81d6fad8ed3a432c2d294271748f2cfcbb9241235bc8369f5071b'
payload = old[:0x6000000] + firmware
assert len(payload) <= 0x7000000
with (root / 'first-firmware.bin').open('xb') as output:
    output.write(payload)
metadata = {
    'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
    'crc32': '%08x' % (zlib.crc32(payload) & 0xffffffff),
    'firmware_bytes': len(firmware),
    'firmware_crc32': '%08x' % (zlib.crc32(firmware) & 0xffffffff),
}
(root / 'transfer.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps(metadata), flush=True)
