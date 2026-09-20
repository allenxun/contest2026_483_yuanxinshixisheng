import tempfile,unittest
from unittest.mock import AsyncMock,patch
from .photo_gateway import PhotoGateway

class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def run_capture(self,gateway,parts):
        reader=AsyncMock(side_effect=parts);writer=AsyncMock()
        result=await gateway.receive(None,None,reader,writer)
        return result,writer
    def parts(self,image=b'\xff\xd8xx\xff\xd9'):
        return [(b'M',b'k7-0000000000000001-1'),(b'F',image),(b'L',image),(b'R',image),(b'E',b'')]
    async def test_three_views_commit_accept_and_same_key_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            auth=type('Auth',(),{'session_token':AsyncMock(return_value='private-token')})()
            gateway=PhotoGateway(auth,folder)
            accepted={'taskId':'11111111-1111-4111-8111-111111111111','accepted':True,'report_ready':False}
            submit=AsyncMock(return_value=accepted)
            with patch('host.whole_device.photo_gateway.upload',submit):
                result,writer=await self.run_capture(gateway,self.parts())
                await self.run_capture(gateway,self.parts())
            self.assertTrue(result['photo_upload_accepted'])
            self.assertEqual(submit.await_args_list[0].args[3].idempotency_key,submit.await_args_list[1].args[3].idempotency_key)
            self.assertEqual(writer.await_args.args[1],b'K')
    async def test_no_commit_does_not_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            gateway=PhotoGateway(None,folder);submit=AsyncMock()
            parts=self.parts();parts[-1]=(b'X',b'')
            with patch('host.whole_device.photo_gateway.upload',submit):
                with self.assertRaises(ValueError):await self.run_capture(gateway,parts)
            submit.assert_not_awaited()
    async def test_wrong_order_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            parts=self.parts();parts[1],parts[2]=parts[2],parts[1]
            with self.assertRaises(ValueError):await self.run_capture(PhotoGateway(None,folder),parts)
    async def test_same_capture_different_photos_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            auth=type('Auth',(),{'session_token':AsyncMock(return_value='token')})();gateway=PhotoGateway(auth,folder)
            with patch('host.whole_device.photo_gateway.upload',AsyncMock(return_value={'taskId':'11111111-1111-4111-8111-111111111111'})) as submit:
                await self.run_capture(gateway,self.parts())
                with self.assertRaisesRegex(ValueError,'capture_content_conflict'):
                    await self.run_capture(gateway,self.parts(b'\xff\xd8yy\xff\xd9'))
                self.assertEqual(submit.await_count,1)
