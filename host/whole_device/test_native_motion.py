import asyncio
import unittest
from .native_motion import NativeMotion
from .serial_owner import SerialOwner
from .test_serial_owner import Port


class NativeMotionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.port=Port();self.owner=SerialOwner(self.port);self.owner.start()
        self.motion=NativeMotion(self.owner)
    async def asyncTearDown(self):await self.owner.close()

    async def test_acceptance_is_not_readiness(self):
        job=asyncio.create_task(self.motion.set_mode('track'))
        while not self.port.written:await asyncio.sleep(.001)
        self.port.incoming.put(b'VOICE MODE requested=1 result=0\n')
        await asyncio.sleep(.02)
        self.assertFalse(job.done())
        self.port.incoming.put(b'VOICE MODE applied=1 result=0\n')
        self.assertTrue(await asyncio.wait_for(job,1))

    async def test_absent_session_fails_without_success(self):
        job=asyncio.create_task(self.motion.set_mode('photo'))
        while not self.port.written:await asyncio.sleep(.001)
        self.port.incoming.put(b'VOICE MODE requested=2 result=-19\n')
        self.assertFalse(await asyncio.wait_for(job,1))

    async def test_stop_can_interrupt_pending_mode(self):
        job=asyncio.create_task(self.motion.set_mode('track'))
        while not self.port.written:await asyncio.sleep(.001)
        stop=asyncio.create_task(self.motion.stop())
        while len(self.port.written)<2:await asyncio.sleep(.001)
        self.port.incoming.put(b'TRACK halt requested: hold last target; not motor disable.\n')
        self.assertTrue(await asyncio.wait_for(stop,1))
        job.cancel();await asyncio.gather(job,return_exceptions=True)
