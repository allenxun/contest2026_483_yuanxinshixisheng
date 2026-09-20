"""Real brief report to bounded speech packets. No mock narration or AI additions."""
import asyncio
import json
import re
import uuid
import os
from .assessment_result import fetch_result
import httpx


def report_sentences(result):
    status = result['status']
    if status == 'needs_retake':
        names = {'front': '正面', 'left': '左侧', 'right': '右侧'}
        return ['照片需要重新拍摄。请补拍' + '、'.join(names[v] for v in result['requiredViews']) + '照片。']
    if status == 'failed':
        return ['本次皮肤检测未能完成，请查看检测失败信息。']
    if status == 'task_replaced':
        return ['本次检测已被新任务替换，请等待新任务的报告。']
    if status != 'report_ready':
        return ['报告仍在分析中，请稍后查询。']
    brief = result['brief']
    conclusion, description = brief.get('conclusion'), brief.get('description')
    if conclusion is not None and not isinstance(conclusion, str):
        raise ValueError('invalid_report_conclusion')
    if description is not None and not isinstance(description, str):
        raise ValueError('invalid_report_description')
    text = '皮肤检测报告已生成。'
    if conclusion:
        text += '报告结论为：' + conclusion + '。'
    if description:
        text += description
    else:
        text += '后端暂未提供详细说明。'
    if len(text) > 2400:
        raise ValueError('report_text_too_long')
    parts = []
    for sentence in re.split(r'(?<=[。！？；\n])', text):
        sentence = sentence.strip()
        parts.extend(sentence[i:i+80] for i in range(0, len(sentence), 80))
    return parts


async def deliver_report(auth, reader, writer, read_packet, packet, synthesize, base):
    kind, body = await read_packet(reader, 36)
    if kind != b'R' or len(body) != 36:
        raise ValueError('invalid_report_task')
    task_id = str(uuid.UUID(body.decode('ascii')))
    async def with_waits(awaitable):
        job = asyncio.create_task(awaitable)
        try:
            while not job.done():
                done, _ = await asyncio.wait({job}, timeout=5)
                if not done:
                    await packet(writer, b'W', b'')
            return await job
        finally:
            if not job.done():
                job.cancel()
            await asyncio.gather(job, return_exceptions=True)

    async with httpx.AsyncClient() as client:
        for attempt in range(60):
            result = await with_waits(fetch_result(auth, task_id, client))
            if result['status'] not in ('queued', 'analyzing'):
                break
            await packet(writer, b'W', b'')
            if attempt < 59:
                await asyncio.sleep(5)
        status = {k: v for k, v in result.items() if k != 'brief'}
        await packet(writer, b'J', json.dumps(status, ensure_ascii=False).encode())
        narration_mode = os.getenv('K7_REPORT_NARRATION_MODE', 'brief')
        if narration_mode not in ('brief', 'mock-sse', 'real-sse'):
            raise ValueError('invalid_narration_mode')
        async def text_source():
            if result['status'] == 'report_ready' and narration_mode != 'brief':
                from .report_narration import stream_sentences, NarrationContractError
                if narration_mode == 'mock-sse':
                    yield '以下为联调测试文案，不是真实测肤结果。'
                try:
                    async for text in stream_sentences(auth, client, task_id, result['reportId']):
                        yield text
                except NarrationContractError as exc:
                    if exc.code != 'UNSUPPORTED_CONTRACT':
                        raise
                    # The report itself is valid and available, but this
                    # backend deployment cannot narrate its brief payload yet.
                    # Speak only the real brief fields; never insert mock text.
                    for text in report_sentences(result):
                        yield text
            else:
                for text in report_sentences(result): yield text
        audio = asyncio.Queue(maxsize=2)
        async def producer():
            try:
                async for text in text_source():
                    pcm, _ = await synthesize(base, text)
                    await audio.put(bytes(pcm))
                await audio.put(None)
            except Exception as exc:
                await audio.put(exc)
        producer_job = asyncio.create_task(producer())
        count = 0
        try:
            while True:
                pcm = await with_waits(audio.get())
                if pcm is None: break
                if isinstance(pcm, Exception): raise pcm
                # Check again after synthesis; a replaced task must never play its old report.
                fresh = await with_waits(fetch_result(auth, task_id, client))
                if fresh['status'] != result['status'] or fresh.get('reportId') != result.get('reportId'):
                    raise ValueError('report_changed_before_playback')
                await packet(writer, b'D', pcm)
                kind, body = await asyncio.wait_for(read_packet(reader, 0), 45)
                if kind != b'A' or body:
                    raise ValueError('report_playback_not_acknowledged')
                count += 1
        finally:
            if not producer_job.done(): producer_job.cancel()
            await asyncio.gather(producer_job, return_exceptions=True)
        await packet(writer, b'E', b'')
    return {'report_task_id': task_id, 'report_status': result['status'],
            'report_narration_mode': narration_mode, 'report_segments_played': count, 'completed': True}
