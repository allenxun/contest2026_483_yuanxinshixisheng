"""Board acceptance for sequential TTS -> fixed ASR -> TTS arena reuse."""

import hashlib
import json
import re
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
STAMP = time.strftime('%Y%m%d-%H%M%S')
LOG_PATH = HERE / ('speech-runtime-' + STAMP + '.log')
REPORT_PATH = HERE / ('speech-runtime-' + STAMP + '.json')


def storage(output, label):
    pattern = (label.encode() +
               rb'_STORAGE peak=(\d+) live=(\d+) records=(\d+) '
               rb'failures=(\d+)')
    match = re.search(pattern, output)
    if not match:
        raise RuntimeError(label + ' storage report missing')
    peak, live, records, failures = map(int, match.groups())
    if peak <= 0 or records <= 0 or live != 0 or failures != 0:
        raise RuntimeError(label + ' arena accounting failed')
    if peak >= 0x20000000:
        raise RuntimeError(label + ' exceeded 512 MiB arena')
    return {'peak': peak, 'live': live, 'records': records,
            'failures': failures}


with LOG_PATH.open('xb') as log, serial.Serial(
        '/dev/ttyUSB0', 1500000, timeout=.03, write_timeout=2,
        exclusive=True) as port:
    port.dtr = False
    port.rts = False

    def command(text, timeout):
        port.write(text.encode() + b'\r')
        port.flush()
        output = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            block = port.read(8192)
            if block:
                log.write(block)
                log.flush()
                output.extend(block)
                print(block.decode(errors='replace'), end='', flush=True)
            if b'U-Boot SPL' in output or b'PANIC' in output:
                raise RuntimeError('unexpected firmware restart or fault')
            if re.search(rb'nsh>\s*(?:\x1b\[K)?\s*$', output):
                return bytes(output)
        raise RuntimeError('command timeout; no retry or restart sent')

    command('', 5)
    before = command('k7mem status', 10)
    first_tts = command('k7voice tts-smoke', 240)
    if (b'VOICE_TTS result=0' not in first_tts or
            b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0'
            not in first_tts):
        raise RuntimeError('first TTS synthesis or playback failed')
    first_tts_storage = storage(first_tts, 'TTS')

    fixed_asr = command('k7voice asr-model', 240)
    if b'ASR_MODEL result=0' not in fixed_asr:
        raise RuntimeError('fixed ASR regression failed')
    asr_storage = storage(fixed_asr, 'ASR')

    second_tts = command('k7voice tts-smoke', 240)
    if (b'VOICE_TTS result=0' not in second_tts or
            b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0'
            not in second_tts):
        raise RuntimeError('second TTS synthesis or playback failed')
    second_tts_storage = storage(second_tts, 'TTS')
    after = command('k7mem status', 10)

report = {
    'status': 'pass',
    'sequence': ['tts-smoke', 'asr-model', 'tts-smoke'],
    'first_tts_storage': first_tts_storage,
    'asr_storage': asr_storage,
    'second_tts_storage': second_tts_storage,
    'log_sha256': hashlib.sha256(LOG_PATH.read_bytes()).hexdigest(),
    'before_status_sha256': hashlib.sha256(before).hexdigest(),
    'after_status_sha256': hashlib.sha256(after).hexdigest(),
    'human_audibility_confirmed': False,
    'voice_provisioning_tested': False,
}
REPORT_PATH.write_text(json.dumps(report, indent=2) + '\n')
print('\nACCEPTANCE=' + str(REPORT_PATH))
