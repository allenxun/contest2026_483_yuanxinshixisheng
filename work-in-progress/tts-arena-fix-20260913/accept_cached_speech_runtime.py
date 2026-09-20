"""Verify cold/warm ASR and TTS sessions on the RAM-only K7 image."""

import hashlib
import json
import re
import time
from pathlib import Path

import serial


HERE = Path(__file__).resolve().parent
STAMP = time.strftime('%Y%m%d-%H%M%S')
LOG_PATH = HERE / ('speechcache-runtime-' + STAMP + '.log')
REPORT_PATH = HERE / ('speechcache-runtime-' + STAMP + '.json')


def one(pattern, output, label):
    match = re.search(pattern, output)
    if not match:
        raise RuntimeError(label + ' diagnostic missing')
    return match.groups()


def available(output):
    return int(one(rb'MODEL DDR base=60000000 bytes=536870912 free=(\d+) ',
                   output, 'model arena')[0])


def tts_metrics(output, expected_hit):
    hit, initialized, speakers, sid = one(
        rb'TTS_CACHE hit=(\d+) init_seconds=([0-9.]+) speakers=(\d+) sid=(\d+)',
        output, 'TTS cache')
    frames, rate, peak, clipped, cache, seconds, _, _ = one(
        rb'TTS_AUDIO frames=(\d+) rate=(\d+) peak_milli=(\d+) clipped=(\d+) '
        rb'cache=(hit|miss) seconds=([0-9.]+) speakers=(\d+) sid=(\d+)',
        output, 'TTS audio')
    if int(hit) != expected_hit or cache != (b'hit' if expected_hit else b'miss'):
        raise RuntimeError('unexpected TTS cache state')
    if int(speakers) != 174 or int(sid) != 21 or int(rate) != 8000:
        raise RuntimeError('unexpected TTS voice metadata')
    if int(frames) <= 0 or int(peak) <= 0 or int(clipped) != 0:
        raise RuntimeError('invalid TTS PCM diagnostics')
    if b'SOUND playback_gain_db=18 dac_attenuation_db=6 maximum=0' not in output:
        raise RuntimeError('speech gain was not +18 dB')
    if (b'VOICE_TTS result=0' not in output or
            b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0'
            not in output):
        raise RuntimeError('TTS synthesis or playback failed')
    return {'hit': int(hit), 'init_seconds': float(initialized),
            'total_seconds': float(seconds), 'frames': int(frames),
            'peak_milli': int(peak), 'speaker_id': int(sid)}


def asr_metrics(output, expected_hit):
    hit, initialized = one(
        rb'ASR_CACHE hit=(\d+) init_seconds=([0-9.]+)', output, 'ASR cache')
    seconds, text_bytes = one(
        rb'ASR_INFER RESULT seconds=([0-9.]+) bytes=(\d+)', output, 'ASR result')
    if int(hit) != expected_hit or b'ASR_MODEL result=0' not in output:
        raise RuntimeError('ASR recognition or cache state failed')
    return {'hit': int(hit), 'init_seconds': float(initialized),
            'total_seconds': float(seconds), 'text_bytes': int(text_bytes)}


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
        raise RuntimeError('command timeout: ' + text)

    command('', 5)
    free_before = available(command('k7mem status', 10))
    first_tts = tts_metrics(command('k7voice tts-smoke', 240), 0)
    free_tts = available(command('k7mem status', 10))
    second_tts = tts_metrics(command('k7voice tts-smoke', 240), 1)
    first_asr = asr_metrics(command('k7voice asr-model', 240), 0)
    free_asr = available(command('k7mem status', 10))
    second_asr = asr_metrics(command('k7voice asr-model', 240), 1)
    third_tts = tts_metrics(command('k7voice tts-smoke', 240), 1)
    free_final = available(command('k7mem status', 10))

if second_tts['init_seconds'] >= 0.5 or second_asr['init_seconds'] >= 0.5:
    raise RuntimeError('warm session initialization exceeded 0.5 seconds')
if second_asr['total_seconds'] >= first_asr['total_seconds']:
    raise RuntimeError('warm ASR did not improve total inference time')
if free_final <= 0 or free_asr <= 0:
    raise RuntimeError('model arena exhausted')

report = {
    'status': 'pass',
    'sequence': ['tts-cold', 'tts-warm', 'asr-cold', 'asr-warm', 'tts-warm'],
    'tts': [first_tts, second_tts, third_tts],
    'asr': [first_asr, second_asr],
    'arena_free': {'before': free_before, 'after_tts': free_tts,
                   'after_asr': free_asr, 'final': free_final},
    'log_sha256': hashlib.sha256(LOG_PATH.read_bytes()).hexdigest(),
    'ram_only': True,
    'human_voice_confirmed': False,
}
REPORT_PATH.write_text(json.dumps(report, indent=2) + '\n')
print('\nACCEPTANCE=' + str(REPORT_PATH))
