import asyncio
import unittest
from .controller import DeviceController


class Ports:
    def __init__(self):
        self.prompts=[];self.starts=0;self.stops=0
        self.events=[(phase,view) for view in ('front','left','right') for phase in ('aligning','ready','saved')]
        self.ready=True
    async def announce(self,key,generation):self.prompts.append(key)
    async def start_tracking(self,generation):self.starts+=1;return self.ready
    async def stop_tracking(self):self.stops+=1;return True
    async def stop_audio(self):pass
    async def capture_views(self,generation):
        for value in self.events:yield value


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_ack_before_success_and_duplicate_no_motion(self):
        ports=Ports();c=DeviceController(ports)
        self.assertTrue(c.start('tracking_start'))
        self.assertFalse(c.start('tracking_start'))
        await c.operation
        self.assertEqual(c.state,'tracking');self.assertEqual(ports.starts,1)
        self.assertFalse(c.start('tracking_start'))
        self.assertEqual(ports.prompts,['tracking_starting','tracking_ready'])

    async def test_start_failure_never_announces_ready(self):
        ports=Ports();ports.ready=False;c=DeviceController(ports)
        c.start('tracking_start');await c.operation
        self.assertNotIn('tracking_ready',ports.prompts)
        self.assertEqual(c.state,'voice_ready')

    async def test_three_views_in_order_without_fake_upload(self):
        ports=Ports();c=DeviceController(ports)
        c.start('assessment_start');await c.operation
        self.assertEqual([x for x in ports.prompts if x.endswith('_saved')],['front_saved','left_saved','right_saved'])
        self.assertEqual(ports.prompts[-1],'capture_saved_local')
        self.assertNotIn('upload_accepted',ports.prompts)

    async def test_wrong_view_cancels(self):
        ports=Ports();ports.events=[('saved','right')];c=DeviceController(ports)
        c.start('assessment_start');await c.operation
        self.assertEqual(ports.stops,1);self.assertNotIn('right_saved',ports.prompts)

    async def test_stop_while_starting_discards_late_ready(self):
        ports=Ports();began=asyncio.Event()
        async def slow(generation):
            began.set()
            try:await asyncio.sleep(100)
            except asyncio.CancelledError:return True
        ports.start_tracking=slow;c=DeviceController(ports)
        c.start('tracking_start');await began.wait()
        self.assertTrue(await c.stop())
        self.assertEqual(c.state,'voice_ready')
        self.assertNotIn('tracking_ready',ports.prompts)
        self.assertEqual(ports.prompts[-1],'tracking_stopped')

    async def test_unconfirmed_stop_does_not_return_ready(self):
        ports=Ports()
        async def fail():return False
        ports.stop_tracking=fail;c=DeviceController(ports)
        self.assertFalse(await c.stop());self.assertEqual(c.state,'stop_unconfirmed')
        self.assertFalse(c.start('tracking_start'))

    async def test_audio_stop_error_still_stops_tracking(self):
        ports=Ports()
        async def fail():raise OSError('audio failed')
        ports.stop_audio=fail;c=DeviceController(ports)
        self.assertFalse(await c.stop())
        self.assertEqual(ports.stops,1)
        self.assertEqual(c.state,'stop_unconfirmed')
