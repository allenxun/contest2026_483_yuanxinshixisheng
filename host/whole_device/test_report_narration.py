import json
import unittest
from .report_narration import sentences
from .report_audio import report_sentences


def event(kind, seq, **extra):
    data = dict(requestId='request', taskId='task', reportId='report', seq=seq)
    data.update(extra)
    return ['event: '+kind, 'data: '+json.dumps(data, ensure_ascii=False), '']


async def lines(items):
    for line in items: yield line


class NarrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_sentence_before_done(self):
        read_done = []
        async def stream():
            for line in event('start', 1)+event('text_delta', 2, delta='第一句。第二'):
                yield line
            read_done.append(True)
            for line in event('text_delta', 3, delta='句。')+event('done', 4): yield line
        iterator = sentences(stream(), 'task', 'report')
        self.assertEqual(await anext(iterator), '第一句。')
        self.assertFalse(read_done)
        self.assertEqual([x async for x in iterator], ['第二句。'])

    async def test_identity_and_sequence_fail_closed(self):
        for bad in [event('text_delta', 3, delta='错。'),
                    event('text_delta', 2, taskId='old', delta='错。'),
                    event('text_delta', 2, reportId='old', delta='错。')]:
            with self.assertRaises(ValueError):
                _ = [x async for x in sentences(lines(event('start',1)+bad),'task','report')]

    async def test_truncated_stream_does_not_flush_partial(self):
        with self.assertRaisesRegex(ValueError,'incomplete'):
            _ = [x async for x in sentences(lines(event('start',1)+event('text_delta',2,delta='未完成')),'task','report')]

    async def test_error_is_not_report_text(self):
        with self.assertRaises(ValueError):
            _ = [x async for x in sentences(lines(event('start',1)+event('error',2,code='INTERNAL_ERROR')),'task','report')]

    def test_real_brief_does_not_invent_details(self):
        text=''.join(report_sentences({'status':'report_ready','brief':{'conclusion':'balanced','description':None}}))
        self.assertIn('balanced',text)
        self.assertIn('暂未提供详细说明',text)
        self.assertNotIn('分',text)
