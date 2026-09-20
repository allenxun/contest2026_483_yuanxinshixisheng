import asyncio
import queue
import threading
import unittest
from .serial_owner import SerialOwner


class Port:
    def __init__(self):self.incoming=queue.Queue();self.written=[]
    def read(self,n):
        try:return self.incoming.get(timeout=.01)
        except queue.Empty:return b''
    def write(self,data):self.written.append(data);return len(data)
    def flush(self):pass
    def close(self):pass


class SerialTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.port=Port();self.owner=SerialOwner(self.port);self.owner.start()
    async def asyncTearDown(self):await self.owner.close()

    async def test_stop_not_blocked_by_start_response(self):
        start=asyncio.create_task(self.owner.request('start','camera',lambda s:s=='READY'))
        while not self.port.written:await asyncio.sleep(.001)
        stop=asyncio.create_task(self.owner.request('halt','halt',lambda s:s=='HALTED'))
        while len(self.port.written)<2:await asyncio.sleep(.001)
        self.port.incoming.put(b'HAL');self.port.incoming.put(b'TED\r\n')
        self.assertEqual(await asyncio.wait_for(stop,1),'HALTED')
        self.assertFalse(start.done())
        start.cancel();await asyncio.gather(start,return_exceptions=True)

    async def test_unmatched_text_cannot_ack(self):
        self.port.incoming.put(b'NOT READY\n')
        with self.assertRaises(TimeoutError):
            await self.owner.request('a','info',lambda s:s=='READY',timeout=.03)

    async def test_newline_injection_rejected(self):
        with self.assertRaises(ValueError):
            await self.owner.request('a','info\nmove',lambda s:True)
        self.assertEqual(self.port.written,[])

    async def test_cancelled_write_keeps_exclusive_ownership(self):
        began=threading.Event();release=threading.Event()
        original=self.port.write
        def slow_write(data):
            if data==b'camera\r':
                began.set();release.wait(2)
            return original(data)
        self.port.write=slow_write
        start=asyncio.create_task(self.owner.request('start','camera',lambda s:s=='READY'))
        await asyncio.to_thread(began.wait,1)
        start.cancel()
        stop=asyncio.create_task(self.owner.request('stop','halt',lambda s:s=='HALTED'))
        try:
            await asyncio.sleep(.02)
            self.assertEqual(self.port.written,[])
        finally:
            release.set()
        await asyncio.gather(start,return_exceptions=True)
        while len(self.port.written)<2:await asyncio.sleep(.001)
        self.assertEqual(self.port.written,[b'camera\r',b'halt\r'])
        self.port.incoming.put(b'HALTED\n')
        await asyncio.wait_for(stop,1)

    async def test_telemetry_overflow_does_not_block_stop_reply(self):
        events=self.owner.subscribe(1)
        stop=asyncio.create_task(self.owner.request('halt','halt',lambda s:s=='HALTED'))
        while not self.port.written:await asyncio.sleep(.001)
        self.port.incoming.put(b'POSE first\nPOSE second\nHALTED\n')
        self.assertEqual(await asyncio.wait_for(stop,1),'HALTED')
        failure=await events.get()
        self.assertIsInstance(failure,OSError)
        self.assertEqual(str(failure),'serial_telemetry_overflow')

    async def test_close_wakes_telemetry_consumer(self):
        events=self.owner.subscribe()
        await self.owner.close()
        self.assertIsInstance(await asyncio.wait_for(events.get(),1),OSError)
