"""Cloud gateway for explicit board-owned chat rounds; no motion or serial access."""
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from host.whole_device.gimbal_ai import question, GimbalStreamError
from host.whole_device.backend_profile import configured_base_url


class DeviceBackend:
    def __init__(self, auth_path, base_url=None):
        self.auth = json.loads(Path(auth_path).read_text(encoding='utf-8-sig'))
        self.base_url = configured_base_url(self.auth.get('base_url'), base_url)
        self.token, self.expires = None, 0

    async def session_token(self):
        # Refresh before submitting a question; never retry an already sent question.
        if time.time() + 60 >= self.expires:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await client.post(self.base_url + '/api/v1/gimbal-sessions',
                    json={k: self.auth[k] for k in ('credential', 'credentialVersion', 'proof')})
            if response.status_code != 200:
                raise ValueError('device_login_failed')
            data = response.json()['data']
            expiry = datetime.fromisoformat(data['expiresAt'].replace('Z', '+00:00'))
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise ValueError('invalid_device_expiry')
            self.token, self.expires = data['sessionToken'], expiry.timestamp()
        return self.token

    async def answer(self, text):
        await self.session_token()
        answer = None
        async for event in question(self.base_url, self.token, text):
            if event['type'] == 'completed':
                answer = event['text']
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 1000:
            raise ValueError('invalid_chat_answer')
        return answer


class Conversation:
    def __init__(self, backend, clock=time.monotonic):
        self.backend, self.clock = backend, clock
        self.clear()

    def clear(self):
        self.pending = None
        self.outcome = {}

    def completed(self, text):
        if not isinstance(text, str) or len(text) > 2000:
            raise ValueError('invalid_chat_question')
        self.pending = (self.clock(), text.strip())

    async def reply(self, service, synthesize):
        self.outcome = {}
        pending, self.pending = self.pending, None
        if pending is None or self.clock() - pending[0] > 60:
            raise ValueError('no_fresh_chat_question')
        if not pending[1]:
            self.outcome = {'chat_reply_kind': 'silence'}
            return None  # Silence is not a backend question and has no spoken fallback.
        async def answer_audio():
            try:
                answer = await self.backend.answer(pending[1])
                self.outcome = {'chat_reply_kind': 'backend_answer'}
            except GimbalStreamError as exc:
                code = str(exc)
                if code not in ('DEPENDENCY_TIMEOUT', 'DEPENDENCY_UNAVAILABLE'):
                    raise
                # Explicit error notice, never an invented answer or question retry.
                self.outcome = {'chat_reply_kind': 'error_notice', 'chat_backend_error': code}
                answer = ('服务响应超时，请稍后再问一次。' if code == 'DEPENDENCY_TIMEOUT'
                          else '对话服务暂时不可用，请稍后再试。')
            try:
                return await synthesize(service, answer)
            except ValueError as exc:
                if str(exc) != 'tts_too_long':
                    raise
                # The board accepts one bounded clip. State the limitation rather
                # than cutting an answer mid-sentence or terminating all rounds.
                self.outcome = {'chat_reply_kind': 'error_notice',
                                'chat_audio_error': 'tts_too_long'}
                return await synthesize(service, '这次回答太长，暂时无法完整播放。请换一个简短的问题。')
        return await asyncio.wait_for(answer_audio(), 90)
