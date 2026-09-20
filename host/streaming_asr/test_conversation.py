import asyncio,time,struct,unittest
from unittest.mock import AsyncMock,patch
from host.streaming_asr.conversation import Conversation
from host.streaming_asr.board_bridge import session,read_packet,packet

class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_answer_not_echo_and_single_use(self):
        backend=type('Backend',(),{'answer':AsyncMock(return_value='这是后端回答')})()
        chat=Conversation(backend);chat.completed('用户问题')
        synth=AsyncMock(return_value=(bytes(20),2))
        self.assertEqual(await chat.reply('service',synth),(bytes(20),2))
        backend.answer.assert_awaited_once_with('用户问题')
        synth.assert_awaited_once_with('service','这是后端回答')
        with self.assertRaises(ValueError):await chat.reply('service',synth)

    async def test_silence_expiry_and_clear(self):
        backend=type('Backend',(),{'answer':AsyncMock()})();clock=[0]
        chat=Conversation(backend,lambda:clock[0]);synth=AsyncMock()
        chat.completed('  ');self.assertIsNone(await chat.reply('service',synth))
        backend.answer.assert_not_awaited();synth.assert_not_awaited()
        chat.completed('问题');clock[0]=61
        with self.assertRaises(ValueError):await chat.reply('service',synth)
        chat.completed('问题');chat.clear()
        with self.assertRaises(ValueError):await chat.reply('service',synth)

    async def test_failure_has_no_echo_fallback(self):
        backend=type('Backend',(),{'answer':AsyncMock(side_effect=ValueError('backend_failed'))})()
        chat=Conversation(backend);chat.completed('问题');synth=AsyncMock()
        with self.assertRaises(ValueError):await chat.reply('service',synth)
        synth.assert_not_awaited();self.assertIsNone(chat.pending)

    async def test_cancellation_consumes_question(self):
        started=asyncio.Event()
        async def answer(text):started.set();await asyncio.Event().wait()
        backend=type('Backend',(),{})();backend.answer=answer
        chat=Conversation(backend);chat.completed('问题')
        task=asyncio.create_task(chat.reply('service',AsyncMock()))
        await started.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertIsNone(chat.pending)

    async def test_explicit_wire_and_normal_tts_isolation(self):
        backend=type('Backend',(),{'answer':AsyncMock(return_value='回答')})();chat=Conversation(backend)
        async def relay(url,frames,event):
            await event({'type':'ready'})
            async for frame in frames:pass
            await event({'type':'final','text':'问题'})
            await event({'type':'completed'})
        server=await asyncio.start_server(lambda r,w:session(r,w,'service',relay,conversation=chat),'127.0.0.1',0)
        async def connect(mode):
            r,w=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1]);w.write(mode);await w.drain();return r,w
        try:
            r,w=await connect(b'K7S1B');await read_packet(r,8192);await packet(w,b'E',b'')
            await read_packet(r,8192);await read_packet(r,8192);await r.read();w.close();await w.wait_closed()
            self.assertEqual(chat.pending[1],'问题');backend.answer.assert_not_awaited()
            synth=AsyncMock(return_value=(bytes(20),1))
            with patch('host.streaming_asr.board_bridge.synthesize',synth):
                r,w=await connect(b'K7S1P');await packet(w,b'T','固定提示'.encode())
                self.assertEqual((await read_packet(r,8192))[0],b'D');await r.read();w.close();await w.wait_closed()
                self.assertEqual(chat.pending[1],'问题')
                r,w=await connect(b'K7S1C');await packet(w,b'T',b'reply')
                self.assertEqual((await read_packet(r,8192))[0],b'D');await r.read();w.close();await w.wait_closed()
                self.assertEqual(synth.await_args_list[-1].args,('service','回答'))
            backend.answer.assert_awaited_once_with('问题')
        finally:
            server.close();await server.wait_closed()

    async def test_ordinary_asr_cannot_supply_chat_reply(self):
        backend=type('Backend',(),{'answer':AsyncMock()})();chat=Conversation(backend);chat.completed('旧问题')
        async def relay(url,frames,event):
            await event({'type':'ready'})
            async for frame in frames:pass
            await event({'type':'final','text':'新普通识别'})
            await event({'type':'completed'})
        server=await asyncio.start_server(lambda r,w:session(r,w,'service',relay,conversation=chat),'127.0.0.1',0)
        try:
            r,w=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1]);w.write(b'K7S1A')
            await read_packet(r,8192);await packet(w,b'E',b'');await read_packet(r,8192);await read_packet(r,8192);await r.read()
            w.close();await w.wait_closed();self.assertIsNone(chat.pending);backend.answer.assert_not_awaited()
        finally:server.close();await server.wait_closed()

    async def test_dependency_failure_speaks_notice_without_retry(self):
        from host.whole_device.gimbal_ai import GimbalStreamError
        for code in ['DEPENDENCY_TIMEOUT','DEPENDENCY_UNAVAILABLE']:
            backend=type('Backend',(),{'answer':AsyncMock(side_effect=GimbalStreamError(code))})()
            chat=Conversation(backend);chat.completed('用户问题')
            synth=AsyncMock(return_value=(bytes(20),1))
            self.assertEqual(await chat.reply('service',synth),(bytes(20),1))
            backend.answer.assert_awaited_once_with('用户问题')
            self.assertEqual(chat.outcome,{'chat_reply_kind':'error_notice','chat_backend_error':code})
            self.assertNotEqual(synth.await_args.args[1],'用户问题')
            self.assertIn('服务',synth.await_args.args[1])
            self.assertIsNone(chat.pending)

    async def test_auth_failure_is_not_hidden_by_notice(self):
        from host.whole_device.gimbal_ai import GimbalStreamError
        backend=type('Backend',(),{'answer':AsyncMock(side_effect=GimbalStreamError('backend_http_401'))})()
        chat=Conversation(backend);chat.completed('用户问题');synth=AsyncMock()
        with self.assertRaises(GimbalStreamError):await chat.reply('service',synth)
        synth.assert_not_awaited()

    async def test_long_audio_notice_and_next_round(self):
        backend=type('Backend',(),{'answer':AsyncMock(side_effect=['长回答','短回答'])})()
        chat=Conversation(backend)
        synth=AsyncMock(side_effect=[ValueError('tts_too_long'),(bytes(20),1),(bytes(30),2)])
        chat.completed('第一个问题')
        self.assertEqual(await chat.reply('service',synth),(bytes(20),1))
        self.assertEqual(chat.outcome,{'chat_reply_kind':'error_notice','chat_audio_error':'tts_too_long'})
        self.assertIn('无法完整播放',synth.await_args.args[1])
        self.assertEqual(backend.answer.await_count,1)
        chat.completed('第二个问题')
        self.assertEqual(await chat.reply('service',synth),(bytes(30),2))
        self.assertEqual(chat.outcome,{'chat_reply_kind':'backend_answer'})
        self.assertEqual(backend.answer.await_count,2)

    async def test_failed_long_audio_notice_does_not_recurse(self):
        backend=type('Backend',(),{'answer':AsyncMock(return_value='长回答')})()
        chat=Conversation(backend);chat.completed('问题')
        synth=AsyncMock(side_effect=ValueError('tts_too_long'))
        with self.assertRaises(ValueError):await chat.reply('service',synth)
        self.assertEqual(synth.await_count,2)
        backend.answer.assert_awaited_once()
