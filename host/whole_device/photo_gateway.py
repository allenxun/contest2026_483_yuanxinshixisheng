"""Bounded K7 RAM JPEG receiver; backend upload only after explicit E commit."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
from .assessment_upload import prepare_development_submission, upload
import httpx

class PhotoGateway:
    def __init__(self, auth, spool, config_path=None, base_url=None):
        self.auth, self.spool = auth, Path(spool)
        self.config_path, self.base_url = config_path, base_url

    def _check_backend_origin(self, base):
        # DeviceBackend exposes the selected origin.  Keep lightweight test
        # doubles compatible while rejecting a real login/upload split.
        auth_base = getattr(self.auth, 'base_url', None)
        if auth_base is not None and auth_base.rstrip('/') != base.rstrip('/'):
            raise ValueError('backend_environment_mismatch')

    async def receive(self, reader, writer, read_packet, packet):
        kind, body = await read_packet(reader,128)
        if kind != b'M' or not re.fullmatch(rb'k7-[0-9a-f]{16}-[0-9]{1,10}',body):
            raise ValueError('invalid_capture_id')
        capture_id=body.decode('ascii');photos={}
        for marker,view in [(b'F','front'),(b'L','left'),(b'R','right')]:
            kind,image=await asyncio.wait_for(read_packet(reader,1024*1024),30)
            if kind!=marker:raise ValueError('invalid_photo_order')
            photos[view]=image
        kind,body=await read_packet(reader,0)
        if kind!=b'E' or body:raise ValueError('missing_photo_commit')
        # The server lock serializes a capture. Repeated requests retain the same key.
        base,submission=prepare_development_submission(capture_id,photos,config_path=self.config_path,
                                                        base_url=self.base_url)
        self._check_backend_origin(base)
        folder=self.spool/capture_id;folder.mkdir(parents=True,exist_ok=True)
        record=folder/'submission.json'
        if record.exists():
            old=json.loads(record.read_text())
            if any(old.get(k)!=submission.manifest()[k] for k in ('views','consentEvidenceRef','photoVersion')):
                raise ValueError('capture_content_conflict')
            base,submission=prepare_development_submission(capture_id,photos,old['idempotencyKey'],self.config_path,
                                                            self.base_url)
            self._check_backend_origin(base)
        else:
            for view,data in submission.photos:(folder/(view+'.jpg')).write_bytes(data)
            temporary=folder/'submission.tmp'
            temporary.write_text(json.dumps(submission.manifest()),encoding='utf-8')
            temporary.replace(record)
        async def submit():
            token=await self.auth.session_token()
            async with httpx.AsyncClient() as client:
                result=await upload(client,base,token,submission)
            (folder/'accepted.json').write_text(json.dumps(result),encoding='utf-8')
            return result
        job=asyncio.create_task(submit())
        try:
            while not job.done():
                done,_=await asyncio.wait({job},timeout=5)
                if not done:await packet(writer,b'W',b'')
            try:
                result=await job
            except Exception as exc:
                # Keep the board protocol generic (the board only needs X),
                # while preserving a redacted, actionable host-side reason.
                # Never write tokens, image bytes, or response bodies here.
                (folder/'error.json').write_text(json.dumps({
                    'type':type(exc).__name__, 'error':str(exc)[:160],
                    'baseUrl':base, 'captureSessionId':capture_id
                },ensure_ascii=False),encoding='utf-8')
                raise
            await packet(writer,b'K',result['taskId'].encode('ascii'))
            return {'photo_upload_accepted':True,'captureSessionId':capture_id,'taskId':result['taskId']}
        finally:
            if not job.done():job.cancel()
            await asyncio.gather(job,return_exceptions=True)
