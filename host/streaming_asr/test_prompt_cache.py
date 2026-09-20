import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from .board_bridge import PromptCache, session, packet, read_packet


class CacheTests(unittest.TestCase):
    def test_expiry_does_not_extend_on_hit(self):
        now = [10]
        cache = PromptCache(ttl=5, clock=lambda: now[0])
        cache.put('a', b'12')
        now[0] = 14
        self.assertEqual(cache.get('a'), b'12')
        now[0] = 15
        self.assertIsNone(cache.get('a'))
        self.assertEqual(cache.size, 0)

    def test_budget_lru_and_copy(self):
        cache = PromptCache(max_bytes=6, max_entries=2)
        data = bytearray(b'12')
        cache.put('a', data)
        data[0] = 0
        cache.put('b', b'34')
        self.assertEqual(cache.get('a'), b'12')
        cache.put('c', b'5678')
        self.assertIsNone(cache.get('b'))
        self.assertEqual(cache.size, 6)
        cache.put('a', b'90')
        self.assertEqual(cache.size, 6)

    def test_fixed_prompt_survives_overnight_and_cache_pressure(self):
        now = [0]
        cache = PromptCache(max_bytes=6, max_entries=2, ttl=5, clock=lambda: now[0])
        cache.put('fixed', b'12', permanent=True)
        cache.put('temporary', b'34')
        now[0] = 86400
        self.assertEqual(cache.get('fixed'), b'12')
        self.assertIsNone(cache.get('temporary'))
        cache.put('new', b'5678')
        cache.put('too-large', b'123456')
        self.assertEqual(cache.get('fixed'), b'12')
        self.assertEqual(cache.get('new'), b'5678')
        self.assertEqual(cache.size, 6)

    def test_fixed_prompt_budget_and_replacement(self):
        cache = PromptCache(max_bytes=4, max_entries=1)
        cache.put('fixed', b'12', permanent=True)
        cache.put('second', b'34', permanent=True)
        self.assertIsNone(cache.get('second'))
        cache.put('fixed', b'1234')
        self.assertEqual(cache.size, 4)
        self.assertEqual(cache.get('fixed'), b'1234')
        self.assertIsNone(cache.entries['fixed'][0])

    def test_invalid_audio_not_retained(self):
        cache = PromptCache(max_bytes=4)
        for data in (b'', b'1', b'123456'):
            cache.put('a', data)
            self.assertIsNone(cache.get('a'))


class CacheWireTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cache = PromptCache()
        self.tasks = set()
        async def accept(reader, writer):
            task = asyncio.current_task()
            self.tasks.add(task)
            try:
                await session(reader, writer, 'http://test', prompt_cache=self.cache)
            finally:
                self.tasks.discard(task)
        self.server = await asyncio.start_server(accept, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        if self.tasks:
            await asyncio.gather(*self.tasks)

    async def request(self, mode):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        try:
            writer.write(mode)
            await packet(writer, b'T', '云台已启动。'.encode())
            result = await read_packet(reader, 8192)
            await reader.read()
            return result
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_only_explicit_prompt_protocol_reuses_pcm(self):
        synth = AsyncMock(return_value=(b'1234', 10))
        with patch('host.streaming_asr.board_bridge.synthesize', synth):
            for mode in (b'K7S1P', b'K7S1P', b'K7S1T', b'K7S1T'):
                self.assertEqual(await self.request(mode), (b'D', b'1234'))
        self.assertEqual(synth.await_count, 3)
        self.assertIsNone(self.cache.get(('http://other', '云台已启动。')))

    async def test_failed_synthesis_can_retry(self):
        synth = AsyncMock(side_effect=[ValueError('tts_failed'), (b'12', 10)])
        with patch('host.streaming_asr.board_bridge.synthesize', synth):
            self.assertEqual((await self.request(b'K7S1P'))[0], b'X')
            self.assertEqual(await self.request(b'K7S1P'), (b'D', b'12'))
        self.assertEqual(synth.await_count, 2)
