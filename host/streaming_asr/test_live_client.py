import asyncio
import json
import struct
import unittest
from .live_client import relay_live, StreamRelayError


class Socket:
    def __init__(self, bad_ack=False):
        self.queue = asyncio.Queue()
        self.queue.put_nowait(json.dumps({'type':'ready','frame_bytes':640}))
        self.bad_ack=bad_ack
        self.messages=[]

    async def send(self, data):
        self.messages.append(data)
        if isinstance(data, bytes):
            seq=struct.unpack_from('<I',data)[0]
            self.queue.put_nowait(json.dumps({'type':'ack','next_seq':seq+(2 if self.bad_ack else 1)}))
            self.queue.put_nowait(json.dumps({'type':'partial','text':'你好'}))
            self.queue.put_nowait(json.dumps({'type':'final','text':'你好'}))
        elif json.loads(data)['type']=='stop':
            self.queue.put_nowait(json.dumps({'type':'completed'}))

    async def recv(self):
        return await self.queue.get()


class LiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_error_code_survives_relay(self):
        socket=Socket()
        socket.queue.put_nowait(json.dumps({'type':'error','code':'client_audio_timeout'}))
        async def source():
            await asyncio.sleep(10)
            yield bytes(640)
        async def event(e):pass
        with self.assertRaises(StreamRelayError) as caught:
            await relay_live(socket,source(),event)
        self.assertEqual(caught.exception.code,'client_audio_timeout')
        self.assertEqual(StreamRelayError('secret arbitrary text').code,'stream_failed')

    async def test_results_before_source_finishes_and_sentence_final_keeps_recording(self):
        socket=Socket();seen=asyncio.Event();events=[]
        async def source():
            yield bytes(640)
            await asyncio.wait_for(seen.wait(),1)
            yield bytes(640)
        async def event(e):
            events.append(e['type'])
            if e['type']=='final':seen.set()
        result=await relay_live(socket,source(),event)
        self.assertEqual(result,{'frames_sent':2,'frames_acknowledged':2})
        self.assertEqual(events.count('final'),2)
        self.assertEqual(events[-1],'completed')

    async def test_bad_ack_cancels_and_closes_source(self):
        closed=[]
        async def source():
            try:
                yield bytes(640)
                await asyncio.sleep(30)
            finally:closed.append(True)
        async def event(e):pass
        with self.assertRaisesRegex(ValueError,'invalid_ack'):
            await relay_live(Socket(True),source(),event)
        self.assertEqual(closed,[True])

    async def test_bad_frame_never_sent(self):
        socket=Socket()
        async def source():yield bytes(639)
        async def event(e):pass
        with self.assertRaisesRegex(ValueError,'invalid_pcm_frame'):
            await relay_live(socket,source(),event)
        self.assertFalse(any(isinstance(x,bytes) for x in socket.messages))
