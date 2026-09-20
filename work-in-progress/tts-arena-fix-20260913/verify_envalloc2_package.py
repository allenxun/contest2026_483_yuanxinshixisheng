import hashlib
import json
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path('/home/swl/openvela')
BUILD = SDK / 'cmake_out/velavision_spoken_tts_gated_envalloc2_20260914'
TOOLS = SDK / 'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin'
RUNTIME = HERE / 'speech-runtime-gated-envalloc2.arm64.o'
PACKAGE = HERE / 'spoken-tts-gated-envalloc2-prefix.bin'
PREFIX = SDK / 'work/native-asr-model-session/encoder1/encoder-first-firmware.bin'
STORAGE_SOURCE = HERE / 'native_tts_storage.hpp'
EXPECTED_STORAGE_SHA256 = 'ecef857d0f2e1cfaf71a1e6b82b88867c25857673db0305371de8b23a1934acd'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


runtime_result = json.loads((HERE / 'envalloc2-runtime-result.json').read_text())
firmware_result = json.loads((HERE / 'envalloc2-firmware-result.json').read_text())
package_result = json.loads((HERE / 'envalloc2-prefix-package.json').read_text())
nm = str(TOOLS / 'aarch64-none-elf-nm')
readelf = str(TOOLS / 'aarch64-none-elf-readelf')
runtime_nm = subprocess.check_output([nm, '-g', str(RUNTIME)], text=True)
elf_nm = subprocess.check_output([nm, '-g', str(BUILD / 'nuttx')], text=True)
sections = subprocess.check_output([readelf, '-SW', str(BUILD / 'nuttx')], text=True)
required = [
    'k7_asr_audio_text', 'k7_asr_model_session_probe',
    'k7_asr_microphone_text', 'k7_asr_microphone_probe',
    'k7_tts_synthesize', 'k7_speech_runtime_try_acquire',
    'k7_speech_runtime_release',
]

payload = PACKAGE.read_bytes()
firmware = (BUILD / 'nuttx.bin').read_bytes()
prefix = PREFIX.read_bytes()[:0x6000000]
runtime_bytes = RUNTIME.read_bytes()
checks = {
    'runtime_hash': sha(RUNTIME) == runtime_result['output_sha256'],
    'firmware_hash': sha(BUILD / 'nuttx.bin') ==
                     firmware_result['artifacts']['nuttx.bin']['sha256'],
    'package_hash': sha(PACKAGE) == package_result['sha256'],
    'package_prefix': payload[:0x6000000] == prefix,
    'package_firmware': payload[0x6000000:] == firmware,
    'package_bound': len(payload) <= 0x07000000,
    'no_flash_commands': package_result['flash_commands'] is False,
    'runtime_entries_unique': all(runtime_nm.count(' T ' + item + '\n') == 1
                                  for item in required),
    'elf_entries_unique': all(elf_nm.count(' T ' + item + '\n') == 1
                              for item in required),
    'exception_sections': '.eh_frame' in sections and
                          '.gcc_except_table' in sections,
    'shared_runtime_gate': package_result['shared_runtime_gate'] is True,
    'allocator_source_hash': sha(STORAGE_SOURCE) ==
                             EXPECTED_STORAGE_SHA256,
    'allocator_diagnostic_linked': b'SR_ALLOC_FAIL reason=' in runtime_bytes,
}
result = {
    'status': 'pass' if all(checks.values()) else 'fail',
    'checks': checks,
    'runtime': {'bytes': RUNTIME.stat().st_size, 'sha256': sha(RUNTIME)},
    'firmware': firmware_result['artifacts'],
    'package': package_result,
    'required_symbols': required,
    'board_tested': False,
    'emmc_written': False,
}
(HERE / 'envalloc2-package-verification.json').write_text(
    json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if result['status'] != 'pass':
    raise SystemExit(1)



