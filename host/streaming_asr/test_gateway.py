import asyncio
import json
import struct
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from host.streaming_asr.gateway import relay, StreamError, mount_streaming_asr


class Client:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
    async def receive(self):
        return await self.incoming.get()
    async def send_json(self, value):
        await self.outgoing.put(value)
    async def event(self, kind):
        while True:
            result = await asyncio.wait_for(self.outgoing.get(), 2)
            if result['type'] == kind:
                return result


class Upstream:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.sent = []
    async def send(self, data):
        self.sent.append(data)
    async def recv(self):
        return await self.incoming.get()
    async def event(self, kind, sentence=None):
        await self.incoming.put(json.dumps({'header': {'event': kind, 'task_id': 'task'},
            'payload': {'output': {'sentence': sentence or {}}}}))


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client, self.up = Client(), Upstream()
        await self.up.event('task-started')
        self.task = asyncio.create_task(relay(self.client, self.up, 'task', 'paraformer-realtime-v2'))
        await self.client.event('ready')
    async def asyncTearDown(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
    async def audio(self, seq=0, size=640):
        await self.client.incoming.put({'type': 'websocket.receive', 'bytes': struct.pack('<I',seq)+b'\0'*size})
    async def control(self, value):
        await self.client.incoming.put({'type':'websocket.receive','text':json.dumps(value)})
    async def test_duplex_partial_before_stop_and_multiple_sentences(self):
        await self.audio()
        self.assertEqual((await self.client.event('ack'))['next_seq'],1)
        for i in range(2):
            await self.up.event('result-generated',{'text':'测试','sentence_end':False,'begin_time':i*1000})
            self.assertEqual((await self.client.event('partial'))['sentence_id'],i*1000)
            await self.up.event('result-generated',{'text':'测试。','sentence_end':True,'begin_time':i*1000})
            await self.client.event('final')
            self.assertFalse(self.task.done())
        await self.control({'type':'stop','next_seq':1})
        for _ in range(100):
            if any(isinstance(x,str) and 'finish-task' in x for x in self.up.sent): break
            await asyncio.sleep(.001)
        await self.up.event('task-finished')
        await self.client.event('completed')
        await self.task
        self.assertIn(b'\0'*640,self.up.sent)
    async def test_bad_sequence(self):
        await self.audio(3)
        with self.assertRaises(StreamError): await self.task
    async def test_bad_frame(self):
        await self.audio(size=639)
        with self.assertRaises(StreamError): await self.task
    async def test_stop_sequence(self):
        await self.control({'type':'stop','next_seq':1})
        with self.assertRaises(StreamError): await self.task
    async def test_cancel(self):
        await self.control({'type':'cancel'})
        await self.client.event('cancelled')
        await self.task
    async def test_disconnect(self):
        await self.client.incoming.put({'type':'websocket.disconnect'})
        await self.task
    async def test_upstream_failure(self):
        await self.up.event('task-failed')
        with self.assertRaisesRegex(StreamError,'upstream_task_failed'): await self.task
    async def test_heartbeat_ignored(self):
        await self.up.event('result-generated',{'heartbeat':True})
        await self.up.event('result-generated',{'text':'好','sentence_end':False,'begin_time':0})
        self.assertEqual((await self.client.event('partial'))['revision'],1)
    async def test_wrong_task(self):
        await self.up.incoming.put(json.dumps({'header':{'task_id':'other','event':'task-finished'}}))
        with self.assertRaisesRegex(StreamError,'upstream_task_mismatch'): await self.task


class RouteTests(unittest.TestCase):
    def test_no_key_no_connection(self):
        app=FastAPI()
        def connector(*args,**kwargs):
            raise AssertionError('must not connect')
        mount_streaming_asr(app,connector,settings={})
        with TestClient(app).websocket_connect('/asr/stream') as ws:
            ws.send_json({'type':'start','sample_rate':16000,'channels':1,'encoding':'pcm_s16le','frame_ms':20})
            self.assertEqual(ws.receive_json(),{'type':'error','code':'service_not_configured'})
    def test_wrong_format(self):
        app=FastAPI()
        mount_streaming_asr(app,settings={})
        with TestClient(app).websocket_connect('/asr/stream') as ws:
            ws.send_json({'type':'start','sample_rate':24000})
            self.assertEqual(ws.receive_json()['code'],'unsupported_start')


if __name__=='__main__': unittest.main()
