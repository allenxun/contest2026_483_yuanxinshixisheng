import hashlib
import json
import zlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
BUILD = Path('/home/swl/openvela/cmake_out/velavision_spoken_tts_gated_flowfix_20260914')
PREFIX = Path('/home/swl/openvela/work/native-asr-model-session/encoder1/encoder-first-firmware.bin')


def sha(data):
    return hashlib.sha256(data).hexdigest()


result = json.loads((HERE / 'flowfix-firmware-result.json').read_text())
firmware = (BUILD / 'nuttx.bin').read_bytes()
prefix = PREFIX.read_bytes()
if sha(firmware) != result['artifacts']['nuttx.bin']['sha256']:
    raise RuntimeError('firmware hash changed')
if sha(prefix) != '9951c2742be81d6fad8ed3a432c2d294271748f2cfcbb9241235bc8369f5071b':
    raise RuntimeError('encoder prefix hash changed')
payload = prefix[:0x6000000] + firmware
if len(payload) > 0x07000000:
    raise RuntimeError('payload exceeds audited U-Boot download buffer')
(HERE / 'spoken-tts-gated-flowfix-prefix.bin').write_bytes(payload)
record = {
    'bytes': len(payload),
    'sha256': sha(payload),
    'crc32': f'{zlib.crc32(payload) & 0xffffffff:08x}',
    'firmware_bytes': len(firmware),
    'firmware_sha256': sha(firmware),
    'firmware_crc32': f'{zlib.crc32(firmware) & 0xffffffff:08x}',
    'flash_commands': False,
    'shared_runtime_gate': True,
}
(HERE / 'flowfix-prefix-package.json').write_text(
    json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))




