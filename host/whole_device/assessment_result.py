"""Device-authenticated task polling and brief retrieval; never consumes mock SSE."""
import asyncio
import json
from pathlib import Path
from urllib.parse import quote
from .backend_profile import configured_base_url

import httpx


async def fetch_result(auth, task_id, client):
    base = configured_base_url(getattr(auth, 'base_url', None) or auth.auth.get('base_url'))

    async def get(path):
        token = await auth.session_token()
        response = await client.get(base + path,
            headers={'Authorization': 'Bearer ' + token},
            timeout=20, follow_redirects=False)
        body = response.json()
        if response.status_code == 409 and body.get('error', {}).get('code') == 'TASK_REPLACED':
            return None
        response.raise_for_status()
        data = body.get('data')
        if not isinstance(data, dict):
            raise ValueError('invalid_result_data')
        return data

    task = await get('/api/v1/skin-assessment-tasks/' + quote(task_id, safe=''))
    if task is None:
        return {'taskId': task_id, 'status': 'task_replaced'}
    if task.get('taskId') != task_id:
        raise ValueError('task_identity_mismatch')
    status = task.get('status')
    if status not in ('queued', 'analyzing', 'needs_retake', 'failed', 'report_ready'):
        raise ValueError('unknown_task_status')
    result = {'taskId': task_id, 'status': status}
    if status == 'needs_retake':
        views = task.get('requiredViews')
        if not isinstance(views, list) or not views or any(v not in ('front', 'left', 'right') for v in views):
            raise ValueError('invalid_required_views')
        result['requiredViews'] = views
    elif status == 'failed':
        result['failureCode'] = task.get('failureCode')
    elif status == 'report_ready':
        report_id = task.get('reportId')
        if not isinstance(report_id, str) or not report_id:
            raise ValueError('missing_report_id')
        brief = await get('/api/v1/skin-reports/' + quote(report_id, safe='') + '?view=brief')
        if brief is None:
            return {'taskId': task_id, 'status': 'task_replaced'}
        if brief.get('reportId', report_id) != report_id:
            raise ValueError('report_identity_mismatch')
        result.update(reportId=report_id, brief=brief)
    return result


async def watch_spool(auth, spool):
    """Follow the newest accepted task without restarting active audio/video services."""
    completed = set()
    while True:
        records = list(Path(spool).glob('*/accepted.json'))
        if records:
            record = max(records, key=lambda path: path.stat().st_mtime_ns)
            try:
                task_id = json.loads(record.read_text(encoding='utf-8'))['taskId']
                if task_id not in completed:
                    result = await poll_result(auth, task_id, record.parent, attempts=1)
                    if result['status'] not in ('queued', 'analyzing', 'query_error'):
                        completed.add(task_id)
            except (OSError, ValueError, KeyError):
                pass
        await asyncio.sleep(5)


async def poll_result(auth, task_id, folder, attempts=60, interval=5):
    """Bounded polling; result stays private alongside the original photographs."""
    folder = Path(folder)
    async with httpx.AsyncClient() as client:
        for attempt in range(attempts):
            try:
                result = await fetch_result(auth, task_id, client)
            except (httpx.HTTPError, ValueError):
                # Do not persist exception text: it may include private URLs or response bodies.
                result = {'taskId': task_id, 'status': 'query_error'}
            result['pollAttempt'] = attempt + 1
            temporary = folder / 'report-result.tmp'
            temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
            temporary.replace(folder / 'report-result.json')
            if result['status'] not in ('queued', 'analyzing', 'query_error'):
                return result
            if attempt + 1 < attempts:
                await asyncio.sleep(interval)
    return result


if __name__ == '__main__':
    import argparse
    from host.streaming_asr.conversation import DeviceBackend
    parser = argparse.ArgumentParser()
    parser.add_argument('--auth', required=True)
    parser.add_argument('--spool', required=True)
    args = parser.parse_args()
    asyncio.run(watch_spool(DeviceBackend(args.auth), args.spool))


