import asyncio
import tempfile
import unittest
from pathlib import Path
from .photo_capture import PhotoCapture
from host.vision.photo_protocol import FrameCache


class Serial:
    def __init__(self):self.queue=asyncio.Queue();self.commands=[];self.unsubscribed=False
    def subscribe(self):return self.queue
    def unsubscribe(self,q):self.unsubscribed=True
    async def request(self,key,command,predicate,timeout):
        self.commands.append(command)
        _,_,q,e,s,ok=command.split()
        line=f'POSE q={int(q)+1} e={e} y=0 p=0 r=0 v=1 st=0 next=0 done={s}'
        assert predicate(line)
        return line


class Motion:
    def __init__(self,serial):self.serial=serial;self.modes=[]
    async def set_mode(self,mode):
        self.modes.append(mode)
        if mode=='photo':self.serial.queue.put_nowait('VOICE MODE applied=2 result=0')
        return True


class PhotoCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.serial=Serial();self.motion=Motion(self.serial);self.cache=FrameCache()
        self.capture=PhotoCapture(self.serial,self.motion,self.cache,self.temp.name)

    def feed(self,q,side,yaw,frame=True):
        if frame:self.cache.add(dict(sequence=q,jpeg=b'\xff\xd8test\xff\xd9',width=640,height=480,capture_us=1,received_at=1))
        for line in [f'POSE q={q} e=1 y={yaw} p=0 r=0 v=1 st=0 next={side} done=0',
                     f'PHOTO q={q} e=1 s={side} y={yaw} p=0 r=0',
                     f'PHOTOQ q={q} sy={yaw} sp=0 sr=0 sharp=100 size=100']:
            self.serial.queue.put_nowait(line)

    async def test_three_actual_saved_files_before_ack(self):
        stream=self.capture.events()
        for q,side,yaw,view in [(1,1,0,'front'),(2,2,45,'left'),(3,4,-45,'right')]:
            self.assertEqual(await anext(stream),('aligning',view))
            self.feed(q,side,yaw)
            self.assertEqual(await anext(stream),('ready',view))
            self.assertEqual(await anext(stream),('saved',view))
            self.assertEqual(len(list(Path(self.temp.name).rglob('*.jpg'))),q)
        with self.assertRaises(StopAsyncIteration):await anext(stream)
        self.assertEqual(len(self.serial.commands),3)
        self.assertEqual(self.motion.modes,['photo','track'])
        self.assertTrue(self.serial.unsubscribed)

    async def test_missing_exact_frame_never_acknowledged(self):
        stream=self.capture.events();await anext(stream)
        self.feed(1,1,0,frame=False)
        await anext(stream)
        with self.assertRaisesRegex(ValueError,'Exact JPEG'):await anext(stream)
        self.assertEqual(self.serial.commands,[])
        self.assertTrue(self.serial.unsubscribed)

    async def test_invalid_angle_never_announced_ready(self):
        stream=self.capture.events();await anext(stream)
        self.feed(1,1,30)
        with self.assertRaisesRegex(ValueError,'Angle'):await anext(stream)
        self.assertEqual(self.serial.commands,[])

    async def test_slow_speech_does_not_delay_file_ack(self):
        stream=self.capture.events();await anext(stream)
        self.feed(1,1,0)
        self.assertEqual(await anext(stream),('ready','front'))
        # Consumer stops advancing while speaking, but the saver must run.
        async def wait_ack():
            while not self.serial.commands:await asyncio.sleep(.001)
        try:
            await asyncio.wait_for(wait_ack(),1)
            self.assertEqual(len(list(Path(self.temp.name).rglob('*.jpg'))),1)
        finally:await stream.aclose()
