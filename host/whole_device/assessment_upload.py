"""Three-view backend contract. No capture, motion, generated consent or retries."""
from dataclasses import dataclass
import hashlib
import json
import os
import re
import uuid
from pathlib import Path
import httpx
from .backend_profile import configured_base_url

VIEWS = ('front', 'left', 'right')

@dataclass(frozen=True)
class Submission:
    capture_session_id: str
    consent_evidence_ref: str
    idempotency_key: str
    photos: tuple

    @classmethod
    def create(cls, capture_session_id, consent_evidence_ref, photos, idempotency_key=None):
        for value in (capture_session_id, consent_evidence_ref):
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ValueError('missing_capture_or_consent_reference')
        if set(photos) != set(VIEWS):
            raise ValueError('three_exact_views_required')
        copied = []
        for view in VIEWS:
            image = bytes(photos[view])
            if len(image) < 4 or len(image) > 10 * 1024 * 1024:
                raise ValueError('invalid_image_size')
            if not (image.startswith(b'\xff\xd8') and image.endswith(b'\xff\xd9')):
                raise ValueError('camera_jpeg_required')
            copied.append((view, image))
        key = idempotency_key if idempotency_key is not None else str(uuid.uuid4())
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',key):
            raise ValueError('invalid_idempotency_key')
        return cls(capture_session_id, consent_evidence_ref, key, tuple(copied))

    def manifest(self):
        return {'captureSessionId': self.capture_session_id,
                'consentEvidenceRef': self.consent_evidence_ref, 'photoVersion': '1',
                'idempotencyKey': self.idempotency_key,
                'views': {view: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                          for view, data in self.photos}}

async def upload(client, base_url, session_token, submission):
    if not session_token or '\r' in session_token or '\n' in session_token:
        raise ValueError('invalid_session_token')
    metadata = {'photoVersion':'1', 'captureSessionId':submission.capture_session_id,
                'consentEvidenceRef':submission.consent_evidence_ref}
    parts = [('metadata',(None,json.dumps(metadata,ensure_ascii=False),'application/json'))]
    parts += [(view,(view+'.jpg',image,'image/jpeg')) for view,image in submission.photos]
    # The immutable submission and its original key must survive uncertain results.
    response = await client.post(base_url.rstrip('/')+'/api/v1/skin-assessment-tasks',
        headers={'Authorization':'Bearer '+session_token,'Idempotency-Key':submission.idempotency_key},
        files=parts, timeout=60, follow_redirects=False)
    if response.status_code not in (200,202):
        code='http_'+str(response.status_code)
        try:
            body=response.json(); error=body.get('error',{})
            if isinstance(error,dict) and isinstance(error.get('code'),str):code=error['code']
        except (ValueError,AttributeError):pass
        raise ValueError('assessment_upload_rejected:'+code)
    body=response.json();data=body.get('data',{})
    if not isinstance(data,dict) or data.get('status')!='queued' or data.get('photoVersion')!='1':
        raise ValueError('invalid_acceptance')
    try:uuid.UUID(data['taskId'])
    except (KeyError,ValueError,TypeError,AttributeError):raise ValueError('invalid_task_id')
    return {'accepted':True,'report_ready':False,'taskId':data['taskId'],
            'photoVersion':data['photoVersion'],'status':data['status'],
            'idempotencyKey':submission.idempotency_key}

def prepare_development_submission(capture_session_id, photos, idempotency_key=None, config_path=None, base_url=None):
    """Use the user's explicit development reference; never a production default."""
    selected_path = config_path or os.getenv('VELAVISION_ASSESSMENT_CONFIG')
    path = Path(selected_path) if selected_path else Path(__file__).with_name('assessment-upload.dev.json')
    config = json.loads(path.read_text(encoding='utf-8'))
    if config.get('environment') not in ('development', 'cloud'):
        raise ValueError('known_backend_config_required')
    base_url = configured_base_url(config.get('baseUrl'), explicit=base_url)
    submission = Submission.create(capture_session_id, config.get('consentEvidenceRef'), photos, idempotency_key)
    return base_url, submission
