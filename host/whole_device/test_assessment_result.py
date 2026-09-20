import unittest
from unittest.mock import AsyncMock
import httpx
from .assessment_result import fetch_result


class ResultTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, status, replacement=False):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.headers['Authorization'], 'Bearer test-token')
            if len(calls) == 1:
                data = dict(taskId='task', status=status, reportId='report', requiredViews=['right'], failureCode='BAD_IMAGE')
                return httpx.Response(200, json={'data': data})
            self.assertEqual(request.url.path, '/api/v1/skin-reports/report')
            self.assertEqual(request.url.query, b'view=brief')
            if replacement:
                return httpx.Response(409, json={'error': {'code': 'TASK_REPLACED'}})
            return httpx.Response(200, json={'data': {'reportId': 'report', 'summary': 'brief'}})
        auth = type('Auth', (), {'auth': {'base_url': 'http://backend'}, 'session_token': AsyncMock(return_value='test-token')})()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await fetch_result(auth, 'task', client)
        return result, calls

    async def test_pending_never_fetches_report(self):
        for status in ('queued', 'analyzing'):
            result, calls = await self.run_case(status)
            self.assertEqual(result['status'], status)
            self.assertEqual(len(calls), 1)

    async def test_retake_and_failure(self):
        result, calls = await self.run_case('needs_retake')
        self.assertEqual(result['requiredViews'], ['right'])
        self.assertEqual(len(calls), 1)
        result, calls = await self.run_case('failed')
        self.assertEqual(result['failureCode'], 'BAD_IMAGE')
        self.assertEqual(len(calls), 1)

    async def test_ready_uses_returned_report_id(self):
        result, calls = await self.run_case('report_ready')
        self.assertEqual(result['brief']['reportId'], 'report')
        self.assertEqual(len(calls), 2)

    async def test_replaced_between_requests_drops_report(self):
        result, _ = await self.run_case('report_ready', True)
        self.assertEqual(result, {'taskId': 'task', 'status': 'task_replaced'})
