"""Contract adapter for stateless gimbal questions; host integration tests only.

No automatic retry: each request is a new backend question. Tokens stay in headers.
Incremental text is provisional until the authoritative completed answer arrives.
"""
import json
import httpx


class GimbalStreamError(ValueError):
    pass


def strict_json(text):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise GimbalStreamError('duplicate_json_key')
            obj[key] = value
        return obj
    try:
        result = json.loads(text, object_pairs_hook=pairs)
    except (ValueError, TypeError) as exc:
        raise GimbalStreamError('invalid_event_json') from exc
    if not isinstance(result, dict):
        raise GimbalStreamError('invalid_event_object')
    return result


async def parse_events(lines):
    event, data, size = None, [], 0
    terminal, text_count = False, 0
    async for line in lines:
        if len(line) > 65536:
            raise GimbalStreamError('event_too_large')
        if line.startswith(':'):
            continue
        if line:
            size += len(line)
            if size > 65536:
                raise GimbalStreamError('event_too_large')
            field, _, value = line.partition(':')
            value = value[1:] if value.startswith(' ') else value
            if field == 'event':
                if event is not None:
                    raise GimbalStreamError('duplicate_event_field')
                event = value
            elif field == 'data':
                data.append(value)
            elif field not in ('id', 'retry'):
                raise GimbalStreamError('unknown_sse_field')
            continue
        if event is None and not data:
            size = 0
            continue
        if terminal:
            raise GimbalStreamError('event_after_terminal')
        value = strict_json('\n'.join(data))
        if event == 'response.delta':
            delta = value.get('delta')
            if not isinstance(delta, str):
                raise GimbalStreamError('invalid_delta')
            text_count += len(delta)
            if text_count > 100000:
                raise GimbalStreamError('answer_too_large')
            yield {'type': 'delta', 'text': delta}
        elif event == 'response.completed':
            answer = value.get('answerText')
            if not isinstance(answer, str) or len(answer) > 100000:
                raise GimbalStreamError('invalid_answer')
            terminal = True
            yield {'type': 'completed', 'text': answer}
        elif event == 'response.failed':
            code = value.get('code')
            if code not in ('DEPENDENCY_UNAVAILABLE', 'DEPENDENCY_TIMEOUT'):
                code = 'backend_stream_failed'
            raise GimbalStreamError(code)
        elif event != 'response.accepted':
            raise GimbalStreamError('unknown_event')
        event, data, size = None, [], 0
    if event is not None or data or not terminal:
        raise GimbalStreamError('incomplete_stream')


async def question(base, token, text, *, client=None):
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError('invalid_text')
    if not isinstance(token, str) or not token or any(c.isspace() for c in token):
        raise ValueError('invalid_device_token')
    if client is None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10),
                                     follow_redirects=False) as owned:
            async for event in question(base, token, text, client=owned):
                yield event
        return
    async with client.stream('POST', base.rstrip('/') + '/api/v1/gimbal-ai/messages',
                             headers={'Authorization': 'Bearer ' + token,
                                      'Accept': 'text/event-stream'},
                             json={'text': text}, follow_redirects=False) as response:
        if response.status_code != 200:
            raise GimbalStreamError('backend_http_' + str(response.status_code))
        if response.headers.get('content-type', '').split(';')[0].strip().lower() != 'text/event-stream':
            raise GimbalStreamError('invalid_content_type')
        async for event in parse_events(response.aiter_lines()):
            yield event
