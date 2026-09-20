"""Explicit LAN development bridge. No vendor key is sent to the board.

Wire: K7S1A (ASR) or K7S1T (TTS), then type:u8, length:u32be, body.
ASR A = seq:u32le + 640 PCM bytes; E = end. J = gateway JSON event.
TTS T = UTF-8 text, D = complete 16k mono S16LE response. X = error.
"""
import argparse
import asyncio
import json
import os
import time
from pathlib import Path
import struct
import httpx
from .live_client import run_live

MAX_PCM = 960000


class EchoResult:
    """Explicit test mode: one completed ASR result, fresh and single use."""
    def __init__(self):
        self.clear()

    def clear(self):
        job = getattr(self, 'audio_job', None)
        if job is not None and not job.done():
            job.cancel()
        self.audio_job = None
        self.text = ''
        self.completed_at = 0

    def take(self):
        text = self.text
        valid = text and time.monotonic() - self.completed_at <= 60
        if not valid:
            self.clear()
            raise ValueError('no_fresh_asr_result')
        self.text = ''
        self.completed_at = 0
        return text.encode('utf-8')


async def synthesize(base, text):
    began = time.monotonic()
    async with httpx.AsyncClient(timeout=45) as client:
        async with client.stream('POST', base + '/tts', json={'text': text}) as response:
            if response.status_code != 200 or not response.headers.get('content-type', '').startswith('audio/pcm'):
                raise ValueError('tts_failed')
            pcm = bytearray()
            async for chunk in response.aiter_bytes():
                if len(pcm) + len(chunk) > MAX_PCM:
                    raise ValueError('tts_too_long')
                pcm.extend(chunk)
    if not pcm or len(pcm) % 2:
        raise ValueError('invalid_pcm')
    return pcm, round((time.monotonic()-began)*1000)


def observe_job(job):
    if not job.cancelled():
        job.exception()  # Failure is still propagated when the TTS request awaits it.


def display_result(data):
    """Optional private latest-result file for the local test UI, never metrics."""
    name = os.getenv('K7_SPEECH_RESULT_FILE')
    if not name:
        return
    target = Path(name)
    try:
        result = {key: data[key] for key in ('type', 'text', 'revision', 'sentence_id') if key in data}
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        temporary.replace(target)
    except OSError:
        pass  # A local display failure must not interrupt audio delivery.


async def read_packet(reader, limit):
    head = await asyncio.wait_for(reader.readexactly(5), 15)
    kind, size = head[:1], struct.unpack('!I', head[1:])[0]
    if size > limit:
        raise ValueError('packet_too_large')
    return kind, await asyncio.wait_for(reader.readexactly(size), 15)


async def packet(writer, kind, data):
    writer.write(kind + struct.pack('!I', len(data)) + data)
    await asyncio.wait_for(writer.drain(), 10)


async def audio_packet(writer, pcm, interval_ms=0):
    """Preserve one D packet while avoiding a burst into K7's eight-slot RX queue."""
    if not interval_ms:
        await packet(writer, b'D', pcm)
        return
    writer.write(b'D' + struct.pack('!I', len(pcm)))
    for offset in range(0, len(pcm), 1024):
        writer.write(pcm[offset:offset+1024])
        await asyncio.wait_for(writer.drain(), 10)
        if offset + 1024 < len(pcm):
            await asyncio.sleep(interval_ms / 1000)


async def session(reader, writer, base, relay=run_live, echo=None, audio_interval_ms=0, on_recognition=None):
    began=time.monotonic()
    report={'frames':0,'events':[],'completed':False,'error':False,
            'frame_arrival_ms':[]}
    mode = None
    try:
        mode = await asyncio.wait_for(reader.readexactly(5), 10)
        if mode == b'K7S1A':
            finals = {}
            if echo is not None:
                echo.clear()
            async def frames():
                sequence = 0
                while True:
                    kind, data = await read_packet(reader, 644)
                    if kind == b'E' and not data:
                        return
                    if kind != b'A' or len(data) != 644 or struct.unpack_from('<I', data)[0] != sequence:
                        raise ValueError('invalid_audio')
                    sequence += 1
                    report['frames']=sequence
                    report['frame_arrival_ms'].append(round((time.monotonic()-began)*1000))
                    yield data[4:]

            async def event(data):
                if data.get('type') == 'final':
                    finals[data.get('sentence_id', 0)] = data.get('text', '')
                if data.get('type') in ('ready', 'partial', 'final'):
                    display_result(data)
                report['events'].append({'type':data.get('type'),
                    'text_chars':len(data.get('text','')),
                    'elapsed_ms':round((time.monotonic()-began)*1000),
                    'frames_received':report['frames']})
                if data.get('type')=='completed':
                    report['completed']=True
                    if echo is not None:
                        echo.text = ''.join(finals[key] for key in sorted(finals)).strip()
                        echo.completed_at = time.monotonic()
                        if 1 <= len(echo.text) <= 1000:
                            echo.audio_job = asyncio.create_task(synthesize(base, echo.text))
                            echo.audio_job.add_done_callback(observe_job)
                raw = json.dumps(data, ensure_ascii=False).encode()
                if len(raw) > 8192:
                    raise ValueError('event_too_large')
                await packet(writer, b'J', raw)
            url = base.replace('http://', 'ws://', 1).replace('https://', 'wss://', 1)
            await relay(url + '/asr/stream', frames(), event)
            if echo is not None and report['completed']:
                echo.text = ''.join(finals[key] for key in sorted(finals)).strip()
                echo.completed_at = time.monotonic()
                display_result({'type': 'final', 'text': echo.text})
        elif mode in (b'K7S1T', b'K7S1P'):
            audio_job = None
            kind, text = await read_packet(reader, 3000)
            if kind != b'T' or not 1 <= len(text.decode()) <= 1000:
                raise ValueError('invalid_text')
            if echo is not None and mode == b'K7S1T':
                text = echo.take()
                audio_job, echo.audio_job = echo.audio_job, None
                if len(text.decode()) > 1000:
                    raise ValueError('invalid_text')
                report['echo_test'] = True
            tts_begin = time.monotonic()
            pcm, synthesis_ms = await audio_job if audio_job is not None else await synthesize(base, text.decode())
            report['tts_synthesis_ms'] = synthesis_ms
            report['tts_request_wait_ms'] = round((time.monotonic()-tts_begin)*1000)
            report['tts_prefetched'] = audio_job is not None
            delivery_begin = time.monotonic()
            await audio_packet(writer, pcm, audio_interval_ms)
            report['host_audio_enqueue_ms'] = round((time.monotonic()-delivery_begin)*1000)
            report['audio_interval_ms'] = audio_interval_ms
            report['tts_pcm_bytes']=len(pcm)
            report['completed']=True
        else:
            raise ValueError('invalid_mode')
    except (Exception, asyncio.CancelledError) as exc:
        if mode == b'K7S1A' and echo is not None:
            echo.clear()
        report['error']=True
        report['error_type']=type(exc).__name__
        if isinstance(exc, ValueError) and str(exc) in (
            'packet_too_large','invalid_audio','invalid_text','tts_failed',
            'tts_too_long','invalid_pcm','invalid_mode','event_too_large','no_fresh_asr_result'):
            report['error_code']=str(exc)
        try:
            await packet(writer, b'X', b'speech_session_failed')
        except Exception:
            pass
    finally:
        report['duration_ms']=round((time.monotonic()-began)*1000)
        directory=os.getenv('K7_SPEECH_METRICS_DIR')
        if directory:
            try:
                target=Path(directory);target.mkdir(parents=True,exist_ok=True)
                (target/(str(time.time_ns())+'.json')).write_text(json.dumps(report))
            except OSError:
                pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        if mode == b'K7S1A' and on_recognition is not None:
            # Controller also waits for the board's successful capture result.
            on_recognition(dict(finals) if report['completed'] and not report['error'] else None)


async def serve(host, port, base, echo_test=False, audio_interval_ms=0, on_recognition=None):
    lock = asyncio.Lock()
    echo = EchoResult() if echo_test else None
    async def accept(reader, writer):
        if lock.locked():
            writer.close()
            return
        async with lock:
            await session(reader, writer, base, echo=echo, audio_interval_ms=audio_interval_ms,
                          on_recognition=on_recognition)
    server = await asyncio.start_server(accept, host, port, limit=4096)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--host', required=True)
    p.add_argument('--port', type=int, default=8001)
    p.add_argument('--service', default='http://127.0.0.1:8000')
    p.add_argument('--echo-test', action='store_true', help='TTS speaks the latest completed ASR once, within 60 seconds')
    p.add_argument('--audio-interval-ms', type=int, choices=range(0,21), default=0,
                   help='Pace 1024-byte PCM chunks; zero retains the baseline')
    args = p.parse_args()
    asyncio.run(serve(args.host, args.port, args.service.rstrip('/'), args.echo_test, args.audio_interval_ms))
