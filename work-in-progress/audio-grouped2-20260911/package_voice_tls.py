import hashlib
import json
import zlib
from pathlib import Path


root = Path(__file__).resolve().parent
firmware_path = Path('/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/nuttx.bin')
prefix_path = Path('/home/swl/openvela/work/native-asr-model-session/encoder1/encoder-first-firmware.bin')
firmware = firmware_path.read_bytes()
prefix = prefix_path.read_bytes()
assert hashlib.sha256(firmware).hexdigest() == '48af763809ec13b8d0293a2bc10ac6b97a229635f604d44384edeb0c9f9421ac'
assert hashlib.sha256(prefix).hexdigest() == '9951c2742be81d6fad8ed3a432c2d294271748f2cfcbb9241235bc8369f5071b'
payload = prefix[:0x6000000] + firmware
assert len(payload) <= 0x7000000
output_path = root / 'voice-tls-first-firmware.bin'
with output_path.open('xb') as output:
    output.write(payload)
report = {
    'bytes': len(payload),
    'sha256': hashlib.sha256(payload).hexdigest(),
    'crc32': f'{zlib.crc32(payload) & 0xffffffff:08x}',
    'firmware_bytes': len(firmware),
    'firmware_sha256': hashlib.sha256(firmware).hexdigest(),
    'firmware_crc32': f'{zlib.crc32(firmware) & 0xffffffff:08x}',
}
(root / 'voice-tls-transfer.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
