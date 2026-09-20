"""K7 duplex PCM websocket gateway to Alibaba Paraformer realtime.

No credentials or recognized text are logged. One connection is one task.
Sentence finals do not close the stream; task-finished closes it.
"""
import asyncio
import contextlib
import json
import os
import struct
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect

ENDPOINT = 'wss://dashscope.aliyuncs.com/api-ws/v1/inference'
FRAME_BYTES = 640
MAX_FRAMES = 3000  # 60 seconds; explicit stop is still required.


class StreamError(ValueError):
    pass


async def bounded(awaitable, seconds=10, timeout_code='stream_timeout'):
    try:
        return await asyncio.wait_for(awaitable, seconds)
    except asyncio.TimeoutError as exc:
        raise StreamError(timeout_code) from exc


def parse_event(raw, task_id):
    if not isinstance(raw, str) or len(raw) > 65536:
        raise StreamError('invalid_upstream_event')
    event = json.loads(raw)
    if not isinstance(event, dict):
        raise StreamError('invalid_upstream_event')
    header = event.get('header', {})
    if header.get('task_id') != task_id:
        raise StreamError('upstream_task_mismatch')
    if header.get('event') == 'task-failed':
        raise StreamError('upstream_task_failed')
    return header.get('event'), event.get('payload', {})


async def relay(client, upstream, task_id, model):
    await bounded(upstream.send(json.dumps({
        'header': {'action': 'run-task', 'task_id': task_id, 'streaming': 'duplex'},
        'payload': {'task_group': 'audio', 'task': 'asr', 'function': 'recognition',
                    'model': model, 'parameters': {'format': 'pcm', 'sample_rate': 16000,
                        'semantic_punctuation_enabled': False, 'max_sentence_silence': 600},
                    'input': {}}})))
    kind, _ = parse_event(await bounded(upstream.recv()), task_id)
    if kind != 'task-started':
        raise StreamError('upstream_not_started')
    await bounded(client.send_json({'type': 'ready', 'frame_bytes': FRAME_BYTES,
                                    'frame_ms': 20, 'max_frames': MAX_FRAMES}))
    stopped = asyncio.Event()

    async def send_audio():
        seq = 0
        while True:
            message = await bounded(client.receive(), 10, 'client_audio_timeout')
            if message['type'] == 'websocket.disconnect':
                return 'disconnect'
            raw = message.get('bytes')
            if raw is not None:
                if stopped.is_set() or len(raw) != FRAME_BYTES + 4:
                    raise StreamError('invalid_audio_frame')
                number = struct.unpack_from('<I', raw)[0]
                if number != seq or seq >= MAX_FRAMES:
                    raise StreamError('invalid_audio_sequence_or_limit')
                # Await each send: no unbounded application audio queue.
                await bounded(upstream.send(raw[4:]), 5, 'upstream_audio_send_timeout')
                seq += 1
                await bounded(client.send_json({'type': 'ack', 'next_seq': seq}))
                continue
            text = message.get('text', '')
            if len(text) > 1024:
                raise StreamError('control_message_too_large')
            control = json.loads(text)
            if not isinstance(control, dict):
                raise StreamError('invalid_control')
            if control.get('type') == 'cancel':
                await bounded(client.send_json({'type': 'cancelled'}))
                return 'cancel'
            if (control.get('type') != 'stop' or stopped.is_set() or
                    type(control.get('next_seq')) is not int or control['next_seq'] != seq):
                raise StreamError('invalid_stop')
            stopped.set()
            await bounded(upstream.send(json.dumps({
                'header': {'action': 'finish-task', 'task_id': task_id, 'streaming': 'duplex'},
                'payload': {'input': {}}})))
            # Keep receiving cancellation/disconnect while waiting for final results.

    async def receive_results():
        revision = 0
        while True:
            kind, payload = parse_event(await bounded(upstream.recv(), 15, 'upstream_result_timeout'), task_id)
            if kind == 'task-finished':
                if not stopped.is_set():
                    raise StreamError('unexpected_task_finish')
                await bounded(client.send_json({'type': 'completed'}))
                return 'completed'
            if kind != 'result-generated':
                raise StreamError('unexpected_upstream_event')
            sentence = payload.get('output', {}).get('sentence', {})
            if sentence.get('heartbeat') is True:
                continue
            text = sentence.get('text')
            final = sentence.get('sentence_end')
            begin = sentence.get('begin_time')
            if (not isinstance(text, str) or len(text.encode('utf-8')) > 4096 or
                    type(final) is not bool or type(begin) is not int or begin < 0):
                raise StreamError('invalid_recognition_result')
            revision += 1
            await bounded(client.send_json({'type': 'final' if final else 'partial',
                'sentence_id': begin, 'revision': revision, 'text': text}))

    tasks = [asyncio.create_task(send_audio()), asyncio.create_task(receive_results())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=75)
        if not done:
            raise StreamError('session_timeout')
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def mount_streaming_asr(app, connector=connect, settings=None):
    """Mount alongside existing /health, /asr and /tts. Settings injectable for tests."""
    @app.websocket('/asr/stream')
    async def stream(client: WebSocket):
        await client.accept()
        try:
            start = await bounded(client.receive_json(), 5)
            if start != {'type': 'start', 'sample_rate': 16000, 'channels': 1,
                         'encoding': 'pcm_s16le', 'frame_ms': 20}:
                raise StreamError('unsupported_start')
            cfg = settings if settings is not None else os.environ
            key = cfg.get('ALIYUN_API_KEY', '').strip()
            model = cfg.get('ALIYUN_STREAMING_ASR_MODEL', 'paraformer-realtime-v2')
            if not key or key.startswith('replace-with-'):
                raise StreamError('service_not_configured')
            if model != 'paraformer-realtime-v2':
                raise StreamError('unsupported_streaming_model')
            async with connector(ENDPOINT, additional_headers={'Authorization': 'Bearer '+key},
                                 open_timeout=10, close_timeout=3, max_size=65536,
                                 max_queue=4, write_limit=32768) as upstream:
                await relay(client, upstream, str(uuid.uuid4()), model)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            # Never forward vendor exception text: it may contain headers or transcript.
            code = str(exc) if isinstance(exc, StreamError) else 'stream_failed'
            with contextlib.suppress(Exception):
                await bounded(client.send_json({'type': 'error', 'code': code}), 2)
        finally:
            with contextlib.suppress(Exception):
                await bounded(client.close(), 2)
