import asyncio
import json
import struct
import unittest
import time
import socket
from .board_bridge import session,packet,read_packet,EchoResult,audio_packet
from unittest.mock import AsyncMock, patch


class AudioPacingTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_photo_survives_small_receive_buffer(self):
        completed=asyncio.get_running_loop().create_future()
        async def accept(reader,writer):
            try:completed.set_result(await read_packet(reader,1024*1024))
            except Exception as exc:completed.set_exception(exc)
            finally:writer.close();await writer.wait_closed()
        server=await asyncio.start_server(accept,'127.0.0.1',0,limit=4096)
        for listener in server.sockets:listener.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4096)
        image=bytes(range(256))*360
        try:
            _,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
            await packet(writer,b'F',image)
            self.assertEqual(await asyncio.wait_for(completed,10),(b'F',image))
            writer.close();await writer.wait_closed()
        finally:server.close();await server.wait_closed()
    async def test_pacing_preserves_exact_single_packet(self):
        class Writer:
            def __init__(self):self.data=bytearray()
            def write(self,data):self.data.extend(data)
            async def drain(self):pass
        pcm=bytes(range(256))*250
        for interval in (0,5):
            writer=Writer()
            with patch('host.streaming_asr.board_bridge.asyncio.sleep',new_callable=AsyncMock) as sleep:
                await audio_packet(writer,pcm,interval)
                self.assertEqual(bytes(writer.data),b'D'+struct.pack('!I',len(pcm))+pcm)
                self.assertEqual(sleep.await_count,62 if interval else 0)


class EchoTests(unittest.TestCase):
    def test_fresh_result_is_single_use(self):
        result=EchoResult();result.text='你好';result.completed_at=time.monotonic()
        self.assertEqual(result.take(),'你好'.encode())
        with self.assertRaises(ValueError):result.take()

    def test_stale_and_empty_results_rejected(self):
        result=EchoResult()
        with self.assertRaises(ValueError):result.take()
        result.text='旧文字';result.completed_at=time.monotonic()-61
        with self.assertRaises(ValueError):result.take()
        self.assertEqual(result.text,'')


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seen=[]
        self.echo=None
        async def relay(url,frames,event):
            await event({'type':'ready','frame_bytes':640})
            async for frame in frames:
                self.seen.append(frame)
                await event({'type':'partial','text':'你好'})
            await event({'type':'final','text':'你好'})
            await event({'type':'completed'})
        self.server=await asyncio.start_server(lambda r,w:session(r,w,'http://127.0.0.1:8000',relay,echo=self.echo), '127.0.0.1',0)
        self.reader,self.writer=await asyncio.open_connection('127.0.0.1',self.server.sockets[0].getsockname()[1])

    async def asyncTearDown(self):
        self.writer.close();await self.writer.wait_closed()
        self.server.close();await self.server.wait_closed()

    async def begin(self):
        self.writer.write(b'K7S1A');await self.writer.drain()
        kind,body=await read_packet(self.reader,8192)
        self.assertEqual(json.loads(body)['type'],'ready')

    async def test_partial_arrives_before_end(self):
        await self.begin()
        await packet(self.writer,b'A',struct.pack('<I',0)+bytes(640))
        _,body=await read_packet(self.reader,8192)
        self.assertEqual(json.loads(body)['type'],'partial')
        await packet(self.writer,b'E',b'')
        for expected in ['final','completed']:
            _,body=await read_packet(self.reader,8192)
            self.assertEqual(json.loads(body)['type'],expected)
        self.assertEqual(len(self.seen),1)

    async def test_sequence_gap_rejected(self):
        await self.begin()
        await packet(self.writer,b'A',struct.pack('<I',1)+bytes(640))
        kind,_=await read_packet(self.reader,8192)
        self.assertEqual(kind,b'X');self.assertFalse(self.seen)

    async def test_prefetch_starts_after_completion_without_waiting_for_tts_request(self):
        self.echo=EchoResult()
        self.writer.close();await self.writer.wait_closed()
        self.reader,self.writer=await asyncio.open_connection('127.0.0.1',self.server.sockets[0].getsockname()[1])
        started=asyncio.Event();release=asyncio.Event()
        async def synth(base,text):
            self.assertEqual(text,'你好');started.set()
            await release.wait()
            return bytes(640),100
        with patch('host.streaming_asr.board_bridge.synthesize',side_effect=synth):
            await self.begin()
            await packet(self.writer,b'A',struct.pack('<I',0)+bytes(640))
            await read_packet(self.reader,8192)
            await packet(self.writer,b'E',b'')
            await read_packet(self.reader,8192)
            _,body=await read_packet(self.reader,8192)
            self.assertEqual(json.loads(body)['type'],'completed')
            await asyncio.wait_for(started.wait(),1)
            self.assertFalse(self.echo.audio_job.done())
            release.set()
            self.assertEqual(await self.echo.audio_job,(bytes(640),100))
            self.assertEqual(self.echo.take(),'你好'.encode())

    async def test_oversize_rejected_before_body(self):
        await self.begin()
        self.writer.write(b'A'+struct.pack('!I',1000000));await self.writer.drain()
        kind,_=await read_packet(self.reader,8192)
        self.assertEqual(kind,b'X')

    async def test_stage_prompt_not_replaced_by_echo_text(self):
        self.echo=EchoResult();self.echo.text='上次录音';self.echo.completed_at=time.monotonic()
        self.writer.close();await self.writer.wait_closed()
        self.reader,self.writer=await asyncio.open_connection('127.0.0.1',self.server.sockets[0].getsockname()[1])
        synth=AsyncMock(return_value=(bytes(640),10))
        with patch('host.streaming_asr.board_bridge.synthesize',synth):
            self.writer.write(b'K7S1P');await self.writer.drain()
            await packet(self.writer,b'T','云台已启动。'.encode())
            kind,body=await read_packet(self.reader,8192)
            self.assertEqual(kind,b'D');self.assertEqual(len(body),640)
            synth.assert_awaited_once_with('http://127.0.0.1:8000','云台已启动。')
        self.assertEqual(self.echo.text,'上次录音')
