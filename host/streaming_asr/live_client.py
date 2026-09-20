"""Duplex sender for a live async PCM source; no full-recording buffer."""
import asyncio
import json
import struct
from websockets.asyncio.client import connect

class StreamRelayError(RuntimeError):
    def __init__(self, code):
        allowed={'client_audio_timeout','upstream_audio_send_timeout',
                 'upstream_result_timeout','stream_timeout','upstream_task_failed',
                 'session_timeout','invalid_audio_sequence_or_limit'}
        self.code=code if isinstance(code,str) and code in allowed else 'stream_failed'
        super().__init__(self.code)


async def relay_live(socket, frames, on_event):
    """Consume exact 20-ms frames after ready; callback receives text snapshots.

    frames is an async iterable. Its producer must bound its own queue and
    fail on overflow instead of silently dropping microphone samples.
    """
    await socket.send(json.dumps({'type': 'start', 'sample_rate': 16000,
        'channels': 1, 'encoding': 'pcm_s16le', 'frame_ms': 20}))
    ready = json.loads(await asyncio.wait_for(socket.recv(), 15))
    if ready.get('type') != 'ready' or ready.get('frame_bytes') != 640:
        raise ValueError('invalid_ready')
    await on_event(ready)
    condition = asyncio.Condition()
    sent = 0
    acknowledged = 0
    stopping = False

    async def sender():
        nonlocal sent, stopping
        async for frame in frames:
            if not isinstance(frame, bytes) or len(frame) != 640:
                raise ValueError('invalid_pcm_frame')
            if sent >= 3000:
                raise ValueError('duration_limit')
            async with condition:
                await asyncio.wait_for(condition.wait_for(
                    lambda: sent - acknowledged < 8), 10)
                number = sent
                sent += 1
            await asyncio.wait_for(socket.send(struct.pack('<I', number) + frame), 10)
        async with condition:
            await asyncio.wait_for(condition.wait_for(lambda: acknowledged == sent), 10)
        stopping = True
        await socket.send(json.dumps({'type': 'stop', 'next_seq': sent}))

    async def receiver():
        nonlocal acknowledged
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), 20))
            kind = event.get('type')
            if kind == 'ack':
                number = event.get('next_seq')
                async with condition:
                    if type(number) is not int or number != acknowledged + 1 or number > sent:
                        raise ValueError('invalid_ack')
                    acknowledged = number
                    condition.notify_all()
                continue
            if kind == 'error':
                raise StreamRelayError(event.get('code'))
            if kind not in ('partial', 'final', 'completed'):
                raise ValueError('invalid_event')
            if kind == 'completed' and not stopping:
                raise ValueError('premature_completion')
            await on_event(event)
            if kind == 'completed':
                return

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), 80)
        return {'frames_sent': sent, 'frames_acknowledged': acknowledged}
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        close = getattr(frames, 'aclose', None)
        if close:
            await close()


async def run_live(url, frames, on_event):
    async with connect(url, max_size=65536, max_queue=4) as socket:
        return await relay_live(socket, frames, on_event)
