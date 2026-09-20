import asyncio
import unittest
from .command_session import CommandSession
from .controller import DeviceController
from .test_controller import Ports


class CommandSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_controller_command_chain(self):
        ports = Ports()
        controller = DeviceController(ports)
        session = CommandSession(controller)
        session.begin('recording-1')
        self.assertEqual(await session.accept('recording-1', 0, 'partial', '你好OpenVela'), 'ignored')
        self.assertEqual(ports.starts, 0)
        self.assertEqual(await session.accept('recording-1', 0, 'final', '你好OpenVela。'), 'started')
        await controller.operation
        self.assertEqual(await session.accept('recording-1', 0, 'final', '你好OpenVela。'), 'ignored')
        self.assertEqual(await session.accept('recording-1', 1, 'final', '开始测肤'), 'started')
        await controller.operation
        self.assertEqual(ports.prompts[-1], 'capture_saved_local')
        self.assertEqual(await session.accept('recording-1', 2, 'final', '停止云台'), 'stopped')
        self.assertEqual(controller.state, 'voice_ready')

    async def test_stale_and_discussion_never_move(self):
        ports = Ports(); session = CommandSession(DeviceController(ports))
        session.begin('new')
        self.assertEqual(await session.accept('old', 0, 'final', '你好OpenVela'), 'stale')
        self.assertEqual(await session.accept('new', 0, 'final', '不要你好OpenVela'), 'chat')
        session.end()
        self.assertEqual(await session.accept('new', 1, 'final', '你好OpenVela'), 'stale')
        self.assertEqual(ports.starts, 0)

    async def test_stop_dispatches_motion_during_audio_cleanup(self):
        ports = Ports(); audio_release = asyncio.Event(); motion = asyncio.Event()
        async def slow_audio(): await audio_release.wait()
        async def halt(): motion.set(); return True
        ports.stop_audio = slow_audio; ports.stop_tracking = halt
        session = CommandSession(DeviceController(ports)); session.begin('a')
        stopping = asyncio.create_task(session.accept('a', 0, 'final', '停止云台'))
        try:
            await asyncio.wait_for(motion.wait(), 1)
            self.assertFalse(stopping.done())
        finally:
            audio_release.set()
            await stopping
