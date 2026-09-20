import unittest
from unittest.mock import AsyncMock
from .command_dry_run import CommandDryRun

class DryRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_cached_command_never_calls_tts(self):
        c=CommandDryRun(bytes(20));s=AsyncMock()
        c.completed('启动云台。')
        self.assertEqual(await c.reply('unused',s),(bytes(20),0))
        s.assert_not_awaited()
        self.assertFalse(c.outcome['motion_enabled'])
        with self.assertRaises(ValueError):await c.reply('unused',s)

    async def test_negations_and_other_commands_do_not_match(self):
        c=CommandDryRun(bytes(20));s=AsyncMock()
        for text in ['不要启动云台','停止云台','启动云台可以吗','启动云台启动云台','']:
            c.completed(text);self.assertIsNone(await c.reply('unused',s))
        s.assert_not_awaited()

    async def test_stale_command_rejected(self):
        now=[0];c=CommandDryRun(bytes(20),clock=lambda:now[0]);c.completed('启动云台');now[0]=61
        with self.assertRaises(ValueError):await c.reply('unused',AsyncMock())

    async def test_photo_uses_own_cached_reply_without_synthesis(self):
        c=CommandDryRun(bytes(20),photo_pcm=bytes(30));s=AsyncMock()
        c.completed('开始拍照。');self.assertEqual(await c.reply('unused',s),(bytes(30),0))
        c.completed('不要开始拍照');self.assertIsNone(await c.reply('unused',s))
        s.assert_not_awaited()
