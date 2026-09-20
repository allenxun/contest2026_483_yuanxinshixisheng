import json,unittest
import httpx
from .assessment_upload import Submission,upload

class UploadTests(unittest.IsolatedAsyncioTestCase):
    def make(self):return Submission.create('capture-1','existing-consent-ref',dict.fromkeys(('front','left','right'),b'\xff\xd8xx\xff\xd9'))
    def test_missing_consent_or_view_rejected(self):
        with self.assertRaises(ValueError):Submission.create('capture','',{})
        with self.assertRaises(ValueError):Submission.create('capture','consent',{'front':b'1234'})
    async def test_multipart_and_acceptance_not_report(self):
        submission=self.make();requests=[]
        async def handler(request):
            requests.append(request);await request.aread()
            for name in ['metadata','front','left','right']:self.assertIn(('name="'+name+'"').encode(),request.content)
            self.assertIn(b'"photoVersion": "1"',request.content)
            self.assertEqual(request.headers['Idempotency-Key'],submission.idempotency_key)
            return httpx.Response(202,json={'data':{'status':'queued','photoVersion':'1','taskId':'11111111-1111-4111-8111-111111111111'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await upload(client,'http://backend','test-token',submission)
        self.assertTrue(result['accepted']);self.assertFalse(result['report_ready']);self.assertEqual(len(requests),1)
    async def test_rejection_no_retry(self):
        calls=[]
        async def handler(request):calls.append(1);return httpx.Response(409,json={'error':{'code':'DEVICE_OCCUPIED'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ValueError,'DEVICE_OCCUPIED'):await upload(client,'http://backend','test-token',self.make())
        self.assertEqual(len(calls),1)
    async def test_malformed_acceptance_rejected(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(202,json={'data':{'status':'report_ready'}}))) as client:
            with self.assertRaises(ValueError):await upload(client,'http://backend','test-token',self.make())

    async def test_user_development_reference_is_sent(self):
        from .assessment_upload import prepare_development_submission
        base,submission=prepare_development_submission('actual-capture-session',dict.fromkeys(('front','left','right'),b'\xff\xd8xx\xff\xd9'))
        async def handler(request):
            await request.aread()
            self.assertIn(b'"consentEvidenceRef": "dev-consent"',request.content)
            self.assertIn(b'"captureSessionId": "actual-capture-session"',request.content)
            return httpx.Response(202,json={'data':{'status':'queued','photoVersion':'1','taskId':'11111111-1111-4111-8111-111111111111'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await upload(client,base,'test-token',submission)
        self.assertTrue(result['accepted'])

    def test_cloud_config_can_be_selected_without_changing_default(self):
        from .assessment_upload import prepare_development_submission
        photos = dict.fromkeys(('front', 'left', 'right'), b'\xff\xd8xx\xff\xd9')
        base, _ = prepare_development_submission(
            'cloud-capture', photos,
            config_path=str(__import__('pathlib').Path(__file__).with_name('assessment-upload.cloud.json')))
        self.assertEqual(base, 'https://eveaisia.com/openvela')
