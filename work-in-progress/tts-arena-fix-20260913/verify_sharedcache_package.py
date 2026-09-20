import hashlib
import json
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path('/home/swl/openvela')
BUILD = SDK / 'cmake_out/velavision_spoken_tts_gated_sharedcache_20260914'
TOOLS = SDK / 'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin'
RUNTIME = HERE / 'speech-runtime-gated-sharedcache.arm64.o'
PACKAGE = HERE / 'spoken-tts-gated-sharedcache-prefix.bin'
PREFIX = SDK / 'work/native-asr-model-session/encoder1/encoder-first-firmware.bin'
STORAGE_SOURCE = HERE / 'native_tts_storage.hpp'
ASR_STORAGE_SOURCE = HERE / 'native_model_storage.hpp'
SHARED_SOURCE = HERE / 'shared_runtime.hpp'
SHARED_IMPL = HERE / 'shared_model_runtime.cpp'
EXPECTED_STORAGE_SHA256 = 'a477ed9f48e06dbfa090ad521e3a0a891bc48829c4c4725c25ea739c1fbe9f0c'
EXPECTED_SOUND_SHA256 = '7bed3306139af1ea6c15ec6c6c8da52472e231c2a672bb8aab3ff78c1f0b0456'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


runtime_result = json.loads((HERE / 'sharedcache-runtime-result.json').read_text())
firmware_result = json.loads((HERE / 'sharedcache-firmware-result.json').read_text())
package_result = json.loads((HERE / 'sharedcache-prefix-package.json').read_text())
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
firmware_elf = (BUILD / 'nuttx').read_bytes()
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
    'tts_asr_capacity_match': '#define SR_CAPACITY 4096' in
                              SHARED_SOURCE.read_text() and
                              'shared_model_runtime()' in
                              STORAGE_SOURCE.read_text() and
                              'shared_model_runtime()' in
                              ASR_STORAGE_SOURCE.read_text(),
    'shared_allocator_linked': b'SR_ATTACH registered' in runtime_bytes and
                               b'_ZN2sr20shared_model_runtimeEv' in elf_nm.encode(),
    'shared_impl_hash': sha(SHARED_IMPL) ==
                        '5b5601836f012717c3038cac6909c207b44071326f1ab3551416c128c459c733',
    'allocator_diagnostic_linked': b'SR_ALLOC_FAIL reason=' in runtime_bytes,
    'tts_audio_stats_linked': b'TTS_AUDIO frames=' in runtime_bytes,
    'asr_cache_diagnostic_linked': b'ASR_CACHE hit=' in runtime_bytes and
                                   b'cached_recognizer' in runtime_bytes,
    'tts_cache_diagnostic_linked': b'TTS_CACHE hit=' in runtime_bytes and
                                   b'speakers=' in runtime_bytes and
                                   b'sid=' in runtime_bytes,
    'persistent_cache_manifest': package_result['persistent_asr_cache'] is True and
                                 package_result['persistent_tts_cache'] is True,
    'male_speaker_manifest': package_result['tts_speaker_id'] == 21,
    'speech_gain_manifest': package_result['speech_gain_db'] == 18,
    'speech_gain_source_hash': firmware_result['inputs'][
        'app/k7sound/k7sound_main.c'] == EXPECTED_SOUND_SHA256,
    'panel_status_linked': b'VOICE_PROVISION_STATUS phase=' in firmware_elf,
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
(HERE / 'sharedcache-package-verification.json').write_text(
    json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
if result['status'] != 'pass':
    raise SystemExit(1)








