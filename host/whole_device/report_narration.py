"""Strict task-bound SSE delta adapter for the current backend narration contract."""
import json
import re
from urllib.parse import quote
from .backend_profile import configured_base_url


class NarrationContractError(ValueError):
    """The backend cannot produce narration for this report payload.

    This is distinct from a transport or authorization failure: callers may
    safely fall back to the already-authorized brief report text in this case.
    """

    def __init__(self, code, message=''):
        self.code = code
        self.message = message
        super().__init__(code)


async def sentences(lines, task_id, report_id):
    event = ''; data = []; sequence = 0; request_id = None; pending = ''; total = 0
    async for line in lines:
        if len(line) > 8192:
            raise ValueError('narration_line_too_long')
        if line.startswith(':'):
            continue
        if line:
            field, _, value = line.partition(':')
            if field == 'event': event = value.lstrip(' ')
            if field == 'data': data.append(value.lstrip(' '))
            if sum(map(len, data)) > 8192:
                raise ValueError('narration_event_too_long')
            continue
        if not data:
            event = ''; continue
        message = json.loads('\n'.join(data)); data = []
        sequence += 1
        if (type(message.get('seq')) is not int or message['seq'] != sequence or
            message.get('taskId') != task_id or message.get('reportId') != report_id):
            raise ValueError('narration_identity_or_sequence')
        if sequence == 1:
            request_id = message.get('requestId')
            if event != 'start' or not isinstance(request_id, str) or not request_id:
                raise ValueError('narration_missing_start')
        elif message.get('requestId') != request_id:
            raise ValueError('narration_request_changed')
        elif event == 'text_delta':
            delta = message.get('delta')
            if not isinstance(delta, str): raise ValueError('invalid_narration_delta')
            total += len(delta)
            if total > 6000: raise ValueError('narration_too_long')
            pending += delta
            while pending:
                match = re.search(r'[。！？；\n]', pending)
                length = min(match.end(), 80) if match else (80 if len(pending) >= 80 else 0)
                if not length: break
                text, pending = pending[:length].strip(), pending[length:]
                if text: yield text
        elif event == 'done':
            if pending.strip(): yield pending.strip()
            return
        else:
            raise ValueError('narration_error_or_invalid_event')
        event = ''
    raise ValueError('narration_incomplete')


async def stream_sentences(auth, client, task_id, report_id):
    token = await auth.session_token()
    base = configured_base_url(getattr(auth, 'base_url', None) or auth.auth.get('base_url'))
    url = base + '/api/v1/skin-assessment-tasks/' + quote(task_id, safe='') + '/report-narration-stream'
    async with client.stream('GET', url, headers={'Authorization': 'Bearer ' + token},
                             timeout=30, follow_redirects=False) as response:
        if response.status_code == 422:
            # The current backend is fail-closed when the persisted report has
            # no pores/spots/surface_gloss groups. Preserve that signal so the
            # report player can use the real brief response instead of
            # dropping the complete report playback.
            try:
                body = json.loads((await response.aread()).decode('utf-8'))
                error = body.get('error', {}) if isinstance(body, dict) else {}
                code = error.get('code') if isinstance(error, dict) else None
                message = error.get('message') if isinstance(error, dict) else ''
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                code, message = None, ''
            raise NarrationContractError(code or 'UNSUPPORTED_CONTRACT', message)
        response.raise_for_status()
        if not response.headers.get('content-type', '').startswith('text/event-stream'):
            raise ValueError('narration_not_sse')
        async for text in sentences(response.aiter_lines(), task_id, report_id):
            yield text
