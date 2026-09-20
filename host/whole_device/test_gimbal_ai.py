import unittest
import httpx
from .gimbal_ai import parse_events, question, GimbalStreamError


async def lines(text):
    for line in text.splitlines():
        yield line


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_incremental_and_authoritative_answer(self):
        source = lines('event: response.delta\ndata: {"delta":"你"}\n\n'
                       'event: response.completed\ndata: {"answerText":"你好"}\n\n')
        iterator = parse_events(source)
        self.assertEqual(await anext(iterator), {'type': 'delta', 'text': '你'})
        self.assertEqual(await anext(iterator), {'type': 'completed', 'text': '你好'})
        with self.assertRaises(StopAsyncIteration):
            await anext(iterator)

    async def test_missing_terminal_unknown_duplicate_and_failed(self):
        for source in (
            'event: response.delta\ndata: {"delta":"你好"}\n\n',
            'event: invented\ndata: {}\n\n',
            'event: response.delta\ndata: {"delta":"a","delta":"b"}\n\n',
            'event: response.completed\ndata: {"answerText":"好"}\n\n' * 2,
            'event: response.failed\ndata: {"code":"DEPENDENCY_TIMEOUT"}\n\n',
            'event: response.completed\ndata: {"answerText":"好"}',
        ):
            with self.subTest(source=source), self.assertRaises(GimbalStreamError):
                _ = [e async for e in parse_events(lines(source))]

    async def test_request_contract_and_no_retry(self):
        requests = []
        def handle(request):
            requests.append(request)
            self.assertEqual(request.url.path, '/api/v1/gimbal-ai/messages')
            self.assertEqual(request.headers['authorization'], 'Bearer test-device-token')
            self.assertEqual(request.content, b'{"text":"hello"}')
            return httpx.Response(503, json={'error': 'unavailable'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaisesRegex(GimbalStreamError, 'backend_http_503'):
                _ = [e async for e in question('http://backend', 'test-device-token', 'hello', client=client)]
        self.assertEqual(len(requests), 1)

    async def test_wrong_response_type_and_invalid_input(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={'answer': 'wrong protocol'}))) as client:
            with self.assertRaisesRegex(GimbalStreamError, 'invalid_content_type'):
                _ = [e async for e in question('http://backend', 'test-token', 'hello', client=client)]
            with self.assertRaisesRegex(ValueError, 'invalid_text'):
                _ = [e async for e in question('http://backend', 'test-token', ' ', client=client)]
