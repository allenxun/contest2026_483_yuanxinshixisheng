"""Report narration core. Transport events require a confirmed backend adapter.

No endpoint, credentials, motor commands, or automatic hardware playback here.
Callbacks must cancel cooperatively; stop_audio must actually stop the player.
"""
import asyncio


class ReportStreamError(ValueError):
    pass


class SentenceBuffer:
    def __init__(self, limit=64):
        self.limit = limit
        self.text = ''

    def feed(self, delta, final=False):
        self.text += delta
        result = []
        while self.text:
            end = next((i+1 for i, char in enumerate(self.text[:self.limit])
                        if char in '。！？!?；;\n'), None)
            if end is None:
                if len(self.text) >= self.limit:
                    end = self.limit
                elif final:
                    end = len(self.text)
                else:
                    break
            part, self.text = self.text[:end].strip(), self.text[end:]
            if part:
                result.append(part)
        return result


class ReportNarrator:
    def __init__(self, synthesize, play, stop_audio):
        self.synthesize = synthesize
        self.play = play
        self.stop_audio = stop_audio
        self._task = None
        self._generation = 0

    async def stop(self):
        self._generation += 1
        task = self._task
        if task is not None:
            task.cancel()
        # Stop the device first, before waiting for a slow synthesis cancellation.
        try:
            await self.stop_audio()
        finally:
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)

    async def run(self, events, request_id, report_id):
        if self._task is not None:
            raise RuntimeError('narration_busy')
        if not all(isinstance(x, str) and 0 < len(x) <= 128 for x in (request_id, report_id)):
            raise ReportStreamError('invalid_identity')
        self._generation += 1
        generation = self._generation
        self._task = asyncio.current_task()
        sentences, audio = asyncio.Queue(2), asyncio.Queue(2)
        stats = {'sentences': 0, 'played': 0, 'characters': 0}

        def current():
            if generation != self._generation:
                raise asyncio.CancelledError()

        async def receive():
            sequence, started = 0, False
            buffer = SentenceBuffer()
            async for event in events:
                current()
                if (not isinstance(event, dict) or event.get('requestId') != request_id or
                        event.get('reportId') != report_id or type(event.get('seq')) is not int or
                        event['seq'] != sequence):
                    raise ReportStreamError('identity_or_sequence_mismatch')
                sequence += 1
                kind = event.get('type')
                if not started:
                    if kind != 'start':
                        raise ReportStreamError('missing_start')
                    started = True
                    continue
                if kind == 'error':
                    raise ReportStreamError('backend_stream_failed')
                if kind not in ('text_delta', 'done'):
                    raise ReportStreamError('unexpected_event')
                delta = event.get('text', '') if kind == 'text_delta' else ''
                if not isinstance(delta, str) or len(delta) > 4096:
                    raise ReportStreamError('invalid_delta')
                stats['characters'] += len(delta)
                if stats['characters'] > 100000:
                    raise ReportStreamError('report_too_long')
                for part in buffer.feed(delta, final=kind == 'done'):
                    await sentences.put(part)
                if kind == 'done':
                    await sentences.put(None)
                    return
            raise ReportStreamError('stream_ended_without_done')

        async def convert():
            while True:
                text = await sentences.get()
                current()
                if text is None:
                    await audio.put(None)
                    return
                pcm = await self.synthesize(text)
                current()
                if not isinstance(pcm, (bytes, bytearray)) or not pcm or len(pcm) % 2 or len(pcm) > 960000:
                    raise ReportStreamError('invalid_pcm')
                stats['sentences'] += 1
                await audio.put(pcm)

        async def output():
            while True:
                pcm = await audio.get()
                current()
                if pcm is None:
                    return
                await self.play(pcm)
                current()
                stats['played'] += 1

        tasks = [asyncio.create_task(fn()) for fn in (receive, convert, output)]
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), 300)
            return stats
        except BaseException:
            self._generation += 1
            for task in tasks:
                task.cancel()
            await self.stop_audio()
            raise
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            close = getattr(events, 'aclose', None)
            try:
                if close:
                    await close()
            finally:
                self._task = None
