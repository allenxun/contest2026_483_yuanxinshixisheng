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
from collections import OrderedDict
from pathlib import Path
import struct
import socket
import httpx
from .live_client import run_live, StreamRelayError

MAX_PCM = 960000


class PromptCache:
    """Bounded, process-local PCM cache for explicit stage prompts only."""
    def __init__(self, max_bytes=2 * 1024 * 1024, max_entries=16, ttl=300,
                 clock=time.monotonic):
        self.max_bytes, self.max_entries, self.ttl = max_bytes, max_entries, ttl
        self.clock, self.entries, self.size = clock, OrderedDict(), 0

    def _expire(self):
        now = self.clock()
        for key, (expiry, pcm) in list(self.entries.items()):
            if expiry is not None and expiry <= now:
                self.size -= len(pcm)
                del self.entries[key]

    def get(self, key):
        self._expire()
        entry = self.entries.get(key)
        if entry is None:
            return None
        self.entries.move_to_end(key)
        return entry[1]

    def put(self, key, pcm, *, permanent=False):
        self._expire()
        if not pcm or len(pcm) % 2 or len(pcm) > min(MAX_PCM, self.max_bytes):
            return
        if self.max_entries <= 0 or (not permanent and self.ttl <= 0):
            return
        data = bytes(pcm)
        # Fixed startup prompts survive expiry and dynamic cache pressure.
        # Reserve capacity first so rejected insertions leave the cache intact.
        old = self.entries.get(key)
        size = self.size - (len(old[1]) if old else 0) + len(data)
        count = len(self.entries) + (0 if old else 1)
        victims = []
        for candidate, (expiry, audio) in self.entries.items():
            if size <= self.max_bytes and count <= self.max_entries:
                break
            if candidate != key and expiry is not None:
                victims.append(candidate)
                size -= len(audio)
                count -= 1
        if size > self.max_bytes or count > self.max_entries:
            return
        for victim in victims:
            del self.entries[victim]
        expiry = None if permanent or (old and old[0] is None) else self.clock() + self.ttl
        self.entries[key] = (expiry, data)
        self.entries.move_to_end(key)
        self.size = size



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


async def session(reader, writer, base, relay=run_live, echo=None, audio_interval_ms=0, on_recognition=None, prompt_cache=None, conversation=None, photo_gateway=None):
    began=time.monotonic()
    report={'frames':0,'events':[],'completed':False,'error':False,
            'frame_arrival_ms':[]}
    mode = None
    diagnostic = None
    diagnostic_path = None
    try:
        mode = await asyncio.wait_for(reader.readexactly(5), 10)
        report['mode']=mode.decode('ascii',errors='replace') if mode in (b'K7S1A',b'K7S1B',b'K7S1C',b'K7S1P',b'K7S1T',b'K7S1U',b'K7S1R') else 'unknown'
        if mode in (b'K7S1A', b'K7S1B'):
            capture_request = os.getenv('K7_CAPTURE_NEXT_PCM')
            if capture_request:
                request = Path(capture_request)
                try:
                    request.unlink()
                    diagnostic = bytearray()
                    diagnostic_path = request.with_suffix('.wav')
                except FileNotFoundError:
                    pass
            finals = {}
            if conversation is not None:
                conversation.clear()
            if mode == b'K7S1B' and conversation is None:
                raise ValueError('chat_disabled')
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
                    if diagnostic is not None and len(diagnostic) < 96000:
                        diagnostic.extend(data[4:])
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
            if mode == b'K7S1B' and report['completed']:
                conversation.completed(''.join(finals[key] for key in sorted(finals)))
        elif mode == b'K7S1R':
            if photo_gateway is None:
                raise ValueError('report_disabled')
            from host.whole_device.report_audio import deliver_report
            report.update(await deliver_report(photo_gateway.auth, reader, writer,
                read_packet, packet, synthesize, base))
        elif mode == b'K7S1U':
            if photo_gateway is None:
                raise ValueError('photo_upload_disabled')
            report['photo_stage']='metadata'
            async def photo_read(source,limit):
                kind,body=await read_packet(source,limit)
                stages={b'M':'front',b'F':'left',b'L':'right',b'R':'commit',b'E':'backend'}
                report['photo_stage']=stages.get(kind,'invalid_packet')
                if kind in (b'F',b'L',b'R'):report['photo_'+kind.decode()+'_bytes']=len(body)
                return kind,body
            report.update(await photo_gateway.receive(reader,writer,photo_read,packet))
            report['completed']=True
        elif mode == b'K7S1C':
            if conversation is None:
                raise ValueError('chat_disabled')
            kind, body = await read_packet(reader, 16)
            if kind != b'T' or body != b'reply':
                raise ValueError('invalid_chat_request')
            job = asyncio.create_task(conversation.reply(base, synthesize))
            try:
                while not job.done():
                    done, _ = await asyncio.wait({job}, timeout=5)
                    if not done:
                        await packet(writer, b'W', b'')
                result = await job
                report.update(conversation.outcome)
                if result is None:
                    await packet(writer, b'N', b'')
                    report['no_speech'] = True
                else:
                    pcm, elapsed = result
                    await audio_packet(writer, pcm, audio_interval_ms)
                    report['tts_pcm_bytes'], report['tts_synthesis_ms'] = len(pcm), elapsed
                report['completed'] = True
            finally:
                if not job.done():
                    job.cancel()
                await asyncio.gather(job, return_exceptions=True)
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
            cache_key = (base, text.decode())
            cache = prompt_cache if mode == b'K7S1P' else None
            pcm = cache.get(cache_key) if cache is not None else None
            report['tts_prompt_cache_hit'] = pcm is not None
            synthesis_ms = 0
            if pcm is None:
                pcm, synthesis_ms = await audio_job if audio_job is not None else await synthesize(base, text.decode())
                if cache is not None:
                    cache.put(cache_key, pcm)
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
        if mode in (b'K7S1A', b'K7S1B') and conversation is not None:
            conversation.clear()
        if mode in (b'K7S1A', b'K7S1B') and echo is not None:
            echo.clear()
        report['error']=True
        report['error_type']=type(exc).__name__
        if isinstance(exc,StreamRelayError):
            report['error_code']=exc.code
        if isinstance(exc, ValueError) and str(exc) in (
            'packet_too_large','invalid_audio','invalid_text','tts_failed',
            'tts_too_long','invalid_pcm','invalid_mode','event_too_large','no_fresh_asr_result'):
            report['error_code']=str(exc)
        if mode==b'K7S1U' and isinstance(exc,ValueError):
            detail=str(exc)
            if detail.startswith('assessment_upload_rejected:'):
                code=detail.partition(':')[2]
                if code and len(code)<=64 and all(c.isascii() and (c.isalnum() or c=='_') for c in code):
                    report['error_code']='assessment_upload_rejected:'+code
        try:
            await packet(writer, b'X', b'speech_session_failed')
        except Exception:
            pass
    finally:
        if diagnostic is not None and diagnostic_path is not None:
            import wave,hashlib
            try:
                with wave.open(str(diagnostic_path), 'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
                    wav.writeframes(diagnostic)
                report['diagnostic_pcm_bytes'] = len(diagnostic)
                report['diagnostic_pcm_sha256'] = hashlib.sha256(diagnostic).hexdigest()
            except OSError:
                report['diagnostic_write_failed'] = True
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


async def serve(host, port, base, echo_test=False, audio_interval_ms=0, on_recognition=None, conversation_auth=None, command_dry_run=False, assessment_auth=None, receive_buffer=0, backend_base_url=None, assessment_config=None):
    lock = asyncio.Lock()
    echo = EchoResult() if echo_test else None
    prompt_cache = PromptCache(max_bytes=8*1024*1024, max_entries=64, ttl=3600) if assessment_auth else PromptCache()
    conversation = None
    if command_dry_run:
        if conversation_auth or echo_test:
            raise ValueError('dry_run_modes_are_exclusive')
        from .command_dry_run import CommandDryRun
        pcm, elapsed = await synthesize(base, '云台已启动')
        photo_pcm, _ = await synthesize(base, '拍照已完成')
        conversation = CommandDryRun(pcm, elapsed, photo_pcm=photo_pcm)
        print('COMMAND_DRY_RUN_READY cached_bytes=%d motion_enabled=0 photo_enabled=0' % (len(pcm)+len(photo_pcm)), flush=True)
    if conversation_auth:
        if echo_test:
            raise ValueError('chat_and_echo_are_exclusive')
        from .conversation import Conversation, DeviceBackend
        conversation = Conversation(DeviceBackend(conversation_auth, base_url=backend_base_url))
    photo_gateway = None
    if assessment_auth:
        if command_dry_run:
            raise ValueError('upload_not_allowed_in_dry_run')
        from .conversation import DeviceBackend
        from host.whole_device.photo_gateway import PhotoGateway
        photo_gateway = PhotoGateway(DeviceBackend(assessment_auth, base_url=backend_base_url),
                                     'private/photo-upload-spool', config_path=assessment_config,
                                     base_url=backend_base_url)
        prompts=json.loads((Path(__file__).parents[1]/'whole_device/voice_prompts.zh-CN.json').read_text(encoding='utf-8'))
        for phrase in prompts.values():
            pcm,_=await synthesize(base,phrase)
            prompt_cache.put((base,phrase),pcm,permanent=True)
        if any(prompt_cache.get((base,phrase)) is None for phrase in prompts.values()):
            raise ValueError('stage_prompt_prewarm_failed')
        print('ASSESSMENT_READY prompts=%d cache_bytes=%d chat_enabled=0' % (len(prompts),prompt_cache.size),flush=True)

    async def accept(reader, writer):
        if lock.locked():
            writer.close()
            return
        async with lock:
            await session(reader, writer, base, echo=echo, audio_interval_ms=audio_interval_ms,
                          on_recognition=on_recognition, prompt_cache=prompt_cache, conversation=conversation, photo_gateway=photo_gateway)
    server = await asyncio.start_server(accept, host, port, limit=4096)
    if receive_buffer:
        for listener in server.sockets:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,receive_buffer)
        print('BOARD_RX_BUFFER requested=%d actual=%d'%(receive_buffer,server.sockets[0].getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF)),flush=True)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--host', required=True)
    p.add_argument('--port', type=int, default=8001)
    p.add_argument('--receive-buffer',type=int,choices=(0,4096),default=0,
                   help='Optional bounded TCP receive window experiment for board photo bursts')
    p.add_argument('--service', default='http://127.0.0.1:8000')
    p.add_argument('--conversation-auth', help='Private device authentication JSON; enables explicit K7S1B/C chat')
    p.add_argument('--assessment-auth', help='Explicit device authentication for RAM photo upload')
    p.add_argument('--backend-base-url', help='Backend origin for login, upload, polling and report narration')
    p.add_argument('--assessment-config', help='Assessment config JSON; defaults to assessment-upload.dev.json')
    p.add_argument('--command-dry-run', action='store_true', help='Audio-only exact command test; no backend or motion')
    p.add_argument('--echo-test', action='store_true', help='TTS speaks the latest completed ASR once, within 60 seconds')
    p.add_argument('--audio-interval-ms', type=int, choices=range(0,21), default=0,
                   help='Pace 1024-byte PCM chunks; zero retains the baseline')
    args = p.parse_args()
    asyncio.run(serve(args.host, args.port, args.service.rstrip('/'), args.echo_test, args.audio_interval_ms,
                      conversation_auth=args.conversation_auth, command_dry_run=args.command_dry_run,
                      assessment_auth=args.assessment_auth, receive_buffer=args.receive_buffer,
                      backend_base_url=args.backend_base_url, assessment_config=args.assessment_config))
